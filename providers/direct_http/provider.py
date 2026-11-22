import os
import re
import uuid
import hashlib
import logging
import httpx
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Awaitable
from urllib.parse import urlparse, unquote

from packages.provider_contracts.base import BaseProviderContract
from packages.shared_schemas.models import (
    FormatOption,
    SourceInspectionResponse,
    SourceType,
    SecurityStatus,
    AcquisitionPermission,
    SourceAccessStatus
)
from apps.api.app.security.ssrf import SSRFValidator
from apps.api.app.security.sanitization import sanitize_filename
from apps.api.app.services.verification import FileVerifier, VerificationResult
from providers.direct_http.chunked_downloader import ChunkedDownloader
from providers.direct_http.safe_http import send_with_safe_redirects

logger = logging.getLogger("aae.direct_http")

def infer_file_type_from_mime(mime: str, filename: str = "") -> str:
    m = (mime or "").lower()
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if "pdf" in m or ext == "pdf":
        return "document"
    if "image/" in m or ext in {"png", "jpg", "jpeg", "gif", "webp", "svg"}:
        return "image"
    if "video/" in m or ext in {"mp4", "mkv", "webm", "avi", "mov"}:
        return "video"
    if "audio/" in m or ext in {"mp3", "wav", "flac", "ogg", "m4a"}:
        return "audio"
    if any(a in m for a in ["zip", "tar", "gzip", "compressed"]) or ext in {"zip", "tar", "gz", "7z", "rar"}:
        return "archive"
    if any(t in m for t in ["text/", "json", "csv", "xml"]):
        return "text"
    return "binary"

MIME_TO_EXTENSION: Dict[str, str] = {
    "text/markdown": ".md",
    "text/x-markdown": ".md",
    "text/plain": ".txt",
    "text/csv": ".csv",
    "application/csv": ".csv",
    "application/json": ".json",
    "text/json": ".json",
    "application/pdf": ".pdf",
    "application/xml": ".xml",
    "text/xml": ".xml",
    "text/html": ".html",
    "application/zip": ".zip",
    "application/gzip": ".gz",
    "application/x-tar": ".tar",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/x-matroska": ".mkv",
    "audio/mpeg": ".mp3",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
}

def extract_filename_from_headers(headers: httpx.Headers, url: str) -> str:
    content_type_raw = headers.get("content-type", "")
    clean_mime = content_type_raw.split(";")[0].strip().lower() if content_type_raw else ""
    mapped_ext = MIME_TO_EXTENSION.get(clean_mime)
    if not mapped_ext and clean_mime:
        import mimetypes
        guessed = mimetypes.guess_extension(clean_mime)
        if guessed and guessed != ".bin":
            mapped_ext = guessed

    cd = headers.get("content-disposition", "")
    if cd:
        match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';]+)["\']?', cd, flags=re.IGNORECASE)
        if match:
            raw_name = unquote(match.group(1).strip())
            if "." not in raw_name and mapped_ext:
                raw_name = f"{raw_name}{mapped_ext}"
            return sanitize_filename(raw_name)

    # Derive from URL path
    path = urlparse(url).path
    base = os.path.basename(path)
    if base:
        unquoted_base = unquote(base).strip()
        if unquoted_base:
            if "." in unquoted_base:
                return sanitize_filename(unquoted_base)
            ext = mapped_ext or ".bin"
            return sanitize_filename(f"{unquoted_base}{ext}")

    ext = mapped_ext or ".bin"
    return sanitize_filename(f"acquired_{uuid.uuid4().hex[:8]}{ext}")

class DirectHTTPProvider(BaseProviderContract):
    """
    Direct HTTP/S file acquisition provider.
    Supports streaming downloads with SSRF validation, chunked SHA-256 calculation,
    redirect validation, and size boundary enforcement.
    """

    @property
    def provider_id(self) -> str:
        return "direct_http"

    @property
    def display_name(self) -> str:
        return "Direct HTTP/S Provider"

    def can_handle(self, url: str) -> bool:
        if not url:
            return False
        parsed = urlparse(url)
        if parsed.scheme.lower() not in {"http", "https"}:
            return False
        # Do not greedily claim known video/media platform domains
        netloc = parsed.netloc.lower()
        excluded_domains = [
            "pin.it", "pinterest.com", "youtube.com", "youtu.be",
            "vimeo.com", "reddit.com", "v.redd.it", "tiktok.com",
            "instagram.com", "twitter.com", "x.com"
        ]
        if any(d in netloc for d in excluded_domains):
            return False
        return True

    async def inspect(self, url: str) -> SourceInspectionResponse:
        is_safe, error = SSRFValidator.validate_url(url)
        if not is_safe:
            return SourceInspectionResponse(
                source_id=f"src_{uuid.uuid4().hex[:12]}",
                url=url,
                resolved_url=url,
                source_type=SourceType.UNSUPPORTED_SOURCE,
                provider_id=self.provider_id,
                is_permitted=False,
                security_status=SecurityStatus.BLOCKED,
                acquisition_permission=AcquisitionPermission.RESTRICTED,
                source_access_status=SourceAccessStatus.BLOCKED,
                capabilities=[],
                mime_type=None,
                estimated_size_bytes=None,
                inspection_status="failed",
                errors=[error or "SSRF check failed."]
            )

        headers = {
            "User-Agent": "agent-acquisition-engine/0.2.0 (+https://github.com/rc710056/agent-acquisition-engine; bot)",
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "en-US,en;q=0.9"
        }
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False, trust_env=False) as client:
            try:
                resp = await send_with_safe_redirects(client, "HEAD", url, headers)
                if resp.status_code == 405 or resp.status_code == 501:
                    await resp.aclose()
                    ranged_headers = dict(headers)
                    ranged_headers["Range"] = "bytes=0-0"
                    resp = await send_with_safe_redirects(client, "GET", url, ranged_headers)

                final_url = str(resp.url)

                if resp.status_code in {403, 429, 503}:
                    return SourceInspectionResponse(
                        source_id=f"src_{uuid.uuid4().hex[:12]}",
                        url=url,
                        resolved_url=final_url,
                        source_type=SourceType.SOURCE_BLOCKED,
                        provider_id=self.provider_id,
                        is_permitted=False,
                        security_status=SecurityStatus.SAFE,
                        acquisition_permission=AcquisitionPermission.RESTRICTED,
                        source_access_status=SourceAccessStatus.BLOCKED,
                        capabilities=[],
                        mime_type=None,
                        estimated_size_bytes=None,
                        inspection_status="blocked",
                        errors=[f"Source-side access blocked (HTTP {resp.status_code}): Automated requests are blocked or rate-limited by the host."]
                    )

                if resp.status_code == 401:
                    return SourceInspectionResponse(
                        source_id=f"src_{uuid.uuid4().hex[:12]}",
                        url=url,
                        resolved_url=final_url,
                        source_type=SourceType.UNSUPPORTED_SOURCE,
                        provider_id=self.provider_id,
                        is_permitted=False,
                        security_status=SecurityStatus.SAFE,
                        acquisition_permission=AcquisitionPermission.USER_AUTHORIZATION_REQUIRED,
                        source_access_status=SourceAccessStatus.AUTHENTICATION_REQUIRED,
                        capabilities=[],
                        mime_type=None,
                        estimated_size_bytes=None,
                        inspection_status="restricted",
                        errors=[f"HTTP server returned status {resp.status_code}: Authentication required."]
                    )

                if resp.status_code >= 400:
                    return SourceInspectionResponse(
                        source_id=f"src_{uuid.uuid4().hex[:12]}",
                        url=url,
                        resolved_url=final_url,
                        source_type=SourceType.UNSUPPORTED_SOURCE,
                        provider_id=self.provider_id,
                        is_permitted=False,
                        security_status=SecurityStatus.SAFE,
                        acquisition_permission=AcquisitionPermission.UNKNOWN,
                        source_access_status=SourceAccessStatus.UNAVAILABLE,
                        capabilities=[],
                        mime_type=None,
                        estimated_size_bytes=None,
                        inspection_status="failed",
                        errors=[f"HTTP server returned error status code {resp.status_code}."]
                    )

                content_type = resp.headers.get("content-type", "application/octet-stream").split(";")[0].strip().lower()
                content_length = resp.headers.get("content-length")
                size_bytes = int(content_length) if (content_length and content_length.isdigit()) else None

                # CRITICAL RULE: text/html is NOT a direct downloadable file!
                if content_type == "text/html":
                    return SourceInspectionResponse(
                        source_id=f"src_{uuid.uuid4().hex[:12]}",
                        url=url,
                        resolved_url=final_url,
                        source_type=SourceType.UNSUPPORTED_SOURCE,
                        provider_id=self.provider_id,
                        is_permitted=False,
                        security_status=SecurityStatus.SAFE,
                        acquisition_permission=AcquisitionPermission.RESTRICTED,
                        source_access_status=SourceAccessStatus.ACCESSIBLE,
                        capabilities=[],
                        mime_type=content_type,
                        estimated_size_bytes=size_bytes,
                        inspection_status="failed",
                        errors=["Direct HTTP Provider does not treat HTML webpages ('text/html') as downloadable files."]
                    )

                capabilities = ["direct_stream"]
                if "bytes" in resp.headers.get("accept-ranges", "").lower():
                    capabilities.extend(["resume", "chunked_download", "concurrent_ranges"])

                filename = extract_filename_from_headers(resp.headers, final_url)
                file_type = infer_file_type_from_mime(content_type, filename)
                format_opt = FormatOption(
                    format_id="original",
                    file_type=file_type,
                    mime_type=content_type,
                    resolution=None,
                    codec=None,
                    estimated_size_bytes=size_bytes,
                    quality_label="original",
                    download_url=final_url
                )

                return SourceInspectionResponse(
                    source_id=f"src_{uuid.uuid4().hex[:12]}",
                    url=url,
                    resolved_url=final_url,
                    source_type=SourceType.DIRECT_FILE,
                    provider_id=self.provider_id,
                    is_permitted=True,
                    security_status=SecurityStatus.SAFE,
                    acquisition_permission=AcquisitionPermission.PERMITTED,
                    source_access_status=SourceAccessStatus.ACCESSIBLE,
                    capabilities=capabilities,
                    mime_type=content_type,
                    estimated_size_bytes=size_bytes,
                    inspection_status="inspected",
                    formats=[format_opt],
                    errors=[]
                )
            except Exception as e:
                return SourceInspectionResponse(
                    source_id=f"src_{uuid.uuid4().hex[:12]}",
                    url=url,
                    resolved_url=url,
                    source_type=SourceType.UNSUPPORTED_SOURCE,
                    provider_id=self.provider_id,
                    is_permitted=False,
                    security_status=SecurityStatus.SAFE,
                    acquisition_permission=AcquisitionPermission.UNKNOWN,
                    source_access_status=SourceAccessStatus.UNAVAILABLE,
                    capabilities=[],
                    mime_type=None,
                    estimated_size_bytes=None,
                    inspection_status="failed",
                    errors=[f"Network inspection error: {str(e)}"]
                )

    async def list_formats(self, url: str) -> List[FormatOption]:
        inspection = await self.inspect(url)
        if not inspection.is_permitted or not inspection.formats:
            return []
        return inspection.formats

    async def check_permissions(self, url: str) -> tuple[bool, List[str]]:
        is_safe, error = SSRFValidator.validate_url(url)
        if not is_safe:
            return False, [error or "SSRF check failed."]
        return True, []

    async def acquire(
        self,
        url: str,
        format_id: str,
        destination_path: Path,
        progress_callback: Optional[Callable[[int, Optional[int]], Awaitable[None]]] = None,
        timeout_seconds: int = 300,
        max_size_bytes: int = 524_288_000,
    ) -> Dict[str, Any]:
        is_safe, error = SSRFValidator.validate_url(url)
        if not is_safe:
            raise ValueError(f"Acquisition blocked by security policy: {error}")

        destination_path.parent.mkdir(parents=True, exist_ok=True)
        extracted_filename = os.path.basename(urlparse(url).path) or "download.bin"
        mime_type = "application/octet-stream"
        total_bytes: Optional[int] = None

        headers = {
            "User-Agent": "agent-acquisition-engine/0.2.0 (+https://github.com/rc710056/agent-acquisition-engine; bot)",
            "Accept": "*/*",
            "Accept-Encoding": "identity"
        }

        # Probe headers for true filename and MIME
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False, trust_env=False) as client:
            try:
                head_resp = await send_with_safe_redirects(client, "HEAD", url, headers)
            except httpx.HTTPError as e:
                logger.warning("Unable to read download metadata for %s: %s", url, e)
            else:
                try:
                    if head_resp.status_code in {405, 501}:
                        await head_resp.aclose()
                        ranged_headers = dict(headers)
                        ranged_headers["Range"] = "bytes=0-0"
                        head_resp = await send_with_safe_redirects(client, "GET", url, ranged_headers)

                    if head_resp.status_code < 400:
                        extracted_filename = extract_filename_from_headers(head_resp.headers, str(head_resp.url))
                        raw_ct = head_resp.headers.get("content-type", "")
                        if raw_ct:
                            parsed_ct = raw_ct.split(";")[0].strip().lower()
                            if parsed_ct:
                                mime_type = parsed_ct
                        cl = head_resp.headers.get("content-length")
                        if cl and cl.isdigit():
                            total_bytes = int(cl)
                        elif "content-range" in head_resp.headers:
                            cr = head_resp.headers.get("content-range", "")
                            match = re.search(r"/(\d+)$", cr)
                            if match:
                                total_bytes = int(match.group(1))
                finally:
                    await head_resp.aclose()

        downloader = ChunkedDownloader(concurrency=4)
        dl_res = await downloader.download(
            url=url,
            destination_path=destination_path,
            total_bytes=total_bytes,
            headers=headers,
            progress_callback=progress_callback,
            timeout_seconds=timeout_seconds,
            max_size_bytes=max_size_bytes
        )

        # Preserve server's content-type from download response if HEAD did not return specific MIME
        dl_mime = (dl_res.get("content_type") or "").strip().lower()
        if dl_mime and (mime_type == "application/octet-stream" or not mime_type):
            mime_type = dl_mime

        # If dl_res has headers and filename was generic, re-extract filename
        if dl_res.get("headers") and (extracted_filename.endswith(".bin") or "." not in extracted_filename):
            extracted_filename = extract_filename_from_headers(dl_res["headers"], url)

        # Check if filename has extension matching known text formats
        text_exts = {
            "md": "text/markdown",
            "markdown": "text/markdown",
            "txt": "text/plain",
            "csv": "text/csv",
            "json": "application/json",
            "pdf": "application/pdf",
            "xml": "application/xml",
        }
        ext_clean = extracted_filename.rsplit(".", 1)[-1].lower() if "." in extracted_filename else ""
        if ext_clean in text_exts and mime_type == "application/octet-stream":
            mime_type = text_exts[ext_clean]

        # Ensure filename extension matches text/csv/json/markdown MIME if it was defaulted to .bin
        if extracted_filename.endswith(".bin") and mime_type in MIME_TO_EXTENSION:
            extracted_filename = f"{extracted_filename[:-4]}{MIME_TO_EXTENSION[mime_type]}"

        return {
            "filename": extracted_filename,
            "mime_type": mime_type,
            "transferred_bytes": dl_res["bytes_downloaded"],
            "total_bytes": total_bytes or dl_res["bytes_downloaded"],
            "sha256": dl_res["sha256"],
            "is_chunked": dl_res.get("is_chunked", False),
            "chunks_count": dl_res.get("chunks_count", 1)
        }

    def verify(
        self,
        file_path: Path,
        expected_size: Optional[int] = None,
        expected_mime: Optional[str] = None,
        expected_sha256: Optional[str] = None,
        expected_file_type: Optional[str] = None,
        **kwargs
    ) -> VerificationResult:
        return FileVerifier.verify_file(
            file_path,
            expected_size=expected_size,
            expected_mime=expected_mime,
            expected_sha256=expected_sha256,
            expected_file_type=expected_file_type
        )
