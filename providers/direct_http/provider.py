import os
import re
import uuid
import hashlib
import httpx
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Awaitable
from urllib.parse import urlparse, unquote

from packages.provider_contracts.base import BaseProviderContract
from packages.shared_schemas.models import FormatOption, SourceInspectionResponse
from apps.api.app.security.ssrf import SSRFValidator
from apps.api.app.security.sanitization import sanitize_filename
from apps.api.app.services.verification import FileVerifier, VerificationResult

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

def extract_filename_from_headers(headers: httpx.Headers, url: str) -> str:
    cd = headers.get("content-disposition", "")
    if cd:
        match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';]+)["\']?', cd, flags=re.IGNORECASE)
        if match:
            raw_name = unquote(match.group(1).strip())
            return sanitize_filename(raw_name)

    # Derive from URL path
    path = urlparse(url).path
    base = os.path.basename(path)
    if base and "." in base:
        return sanitize_filename(unquote(base))

    return sanitize_filename(f"acquired_{uuid.uuid4().hex[:8]}.bin")

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
        return parsed.scheme.lower() in {"http", "https"}

    async def inspect(self, url: str) -> SourceInspectionResponse:
        is_safe, error = SSRFValidator.validate_url(url)
        if not is_safe:
            return SourceInspectionResponse(
                source_id=f"src_{uuid.uuid4().hex[:12]}",
                url=url,
                provider_id=self.provider_id,
                is_permitted=False,
                capabilities=[],
                mime_type=None,
                estimated_size_bytes=None,
                inspection_status="failed",
                errors=[error or "SSRF check failed."]
            )

        headers = {"User-Agent": "AgentAcquisitionEngine/1.0"}
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            try:
                # 1. Try HEAD request first
                resp = await client.head(url, headers=headers)
                if resp.status_code == 405 or resp.status_code == 501:
                    # HEAD not allowed, fallback to ranged GET for 1 byte
                    ranged_headers = dict(headers)
                    ranged_headers["Range"] = "bytes=0-0"
                    resp = await client.get(url, headers=ranged_headers)

                # Check redirect hops if redirect returned
                while resp.is_redirect:
                    next_url = resp.headers.get("location")
                    if not next_url:
                        break
                    # Validate next redirect against SSRF
                    safe_redirect, redirect_err = SSRFValidator.validate_url(next_url)
                    if not safe_redirect:
                        return SourceInspectionResponse(
                            source_id=f"src_{uuid.uuid4().hex[:12]}",
                            url=url,
                            provider_id=self.provider_id,
                            is_permitted=False,
                            capabilities=[],
                            mime_type=None,
                            estimated_size_bytes=None,
                            inspection_status="failed",
                            errors=[f"Redirect to blocked target '{next_url}': {redirect_err}"]
                        )
                    resp = await client.head(next_url, headers=headers)

                if resp.status_code >= 400:
                    return SourceInspectionResponse(
                        source_id=f"src_{uuid.uuid4().hex[:12]}",
                        url=url,
                        provider_id=self.provider_id,
                        is_permitted=False,
                        capabilities=[],
                        mime_type=None,
                        estimated_size_bytes=None,
                        inspection_status="failed",
                        errors=[f"HTTP server returned error status code {resp.status_code}."]
                    )

                content_type = resp.headers.get("content-type", "application/octet-stream").split(";")[0].strip()
                content_length = resp.headers.get("content-length")
                size_bytes = int(content_length) if (content_length and content_length.isdigit()) else None

                capabilities = ["direct_stream"]
                if "bytes" in resp.headers.get("accept-ranges", "").lower():
                    capabilities.append("resume")

                return SourceInspectionResponse(
                    source_id=f"src_{uuid.uuid4().hex[:12]}",
                    url=url,
                    provider_id=self.provider_id,
                    is_permitted=True,
                    capabilities=capabilities,
                    mime_type=content_type,
                    estimated_size_bytes=size_bytes,
                    inspection_status="inspected",
                    errors=[]
                )
            except Exception as e:
                return SourceInspectionResponse(
                    source_id=f"src_{uuid.uuid4().hex[:12]}",
                    url=url,
                    provider_id=self.provider_id,
                    is_permitted=False,
                    capabilities=[],
                    mime_type=None,
                    estimated_size_bytes=None,
                    inspection_status="failed",
                    errors=[f"Network inspection error: {str(e)}"]
                )

    async def list_formats(self, url: str) -> List[FormatOption]:
        inspection = await self.inspect(url)
        mime = inspection.mime_type or "application/octet-stream"
        filename = os.path.basename(urlparse(url).path)
        file_type = infer_file_type_from_mime(mime, filename)

        return [
            FormatOption(
                format_id="original",
                file_type=file_type,
                mime_type=mime,
                resolution=None,
                codec=None,
                estimated_size_bytes=inspection.estimated_size_bytes,
                quality_label="original",
                provider_restrictions=[]
            )
        ]

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
        sha256 = hashlib.sha256()
        transferred_bytes = 0
        total_bytes: Optional[int] = None
        extracted_filename = os.path.basename(urlparse(url).path) or "download.bin"

        headers = {"User-Agent": "AgentAcquisitionEngine/1.0"}

        async with httpx.AsyncClient(timeout=float(timeout_seconds), follow_redirects=True) as client:
            async with client.stream("GET", url, headers=headers) as response:
                if response.status_code >= 400:
                    raise RuntimeError(f"HTTP request failed with status {response.status_code}")

                # Check redirected URL
                final_url = str(response.url)
                safe_final, final_err = SSRFValidator.validate_url(final_url)
                if not safe_final:
                    raise SecurityError(f"Redirected to forbidden address '{final_url}': {final_err}")

                extracted_filename = extract_filename_from_headers(response.headers, final_url)
                cl = response.headers.get("content-length")
                if cl and cl.isdigit():
                    total_bytes = int(cl)
                    if total_bytes > max_size_bytes:
                        raise ValueError(f"Resource size ({total_bytes} bytes) exceeds maximum limit ({max_size_bytes} bytes)")

                mime_type = response.headers.get("content-type", "application/octet-stream").split(";")[0].strip()

                with open(destination_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        if not chunk:
                            continue
                        transferred_bytes += len(chunk)
                        if transferred_bytes > max_size_bytes:
                            raise ValueError(f"Download aborted: file exceeded maximum limit of {max_size_bytes} bytes")

                        sha256.update(chunk)
                        f.write(chunk)

                        if progress_callback:
                            await progress_callback(transferred_bytes, total_bytes)

        return {
            "filename": extracted_filename,
            "mime_type": mime_type,
            "transferred_bytes": transferred_bytes,
            "total_bytes": total_bytes or transferred_bytes,
            "sha256": sha256.hexdigest(),
        }

    def verify(
        self,
        file_path: Path,
        expected_size: Optional[int] = None,
        expected_mime: Optional[str] = None,
        expected_sha256: Optional[str] = None
    ) -> VerificationResult:
        return FileVerifier.verify_file(
            file_path,
            expected_size=expected_size,
            expected_mime=expected_mime,
            expected_sha256=expected_sha256
        )
