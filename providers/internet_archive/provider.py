import os
import re
import uuid
import hashlib
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Awaitable
from urllib.parse import urlparse, unquote
import httpx

from packages.provider_contracts.base import BaseProviderContract
from packages.shared_schemas.models import (
    FormatOption,
    SourceInspectionResponse,
    MediaAsset,
    SourceType,
    SecurityStatus,
    AcquisitionPermission,
    SourceAccessStatus
)
from apps.api.app.security.ssrf import SSRFValidator
from apps.api.app.security.sanitization import sanitize_filename
from apps.api.app.services.verification import FileVerifier, VerificationResult
from providers.direct_http.chunked_downloader import ChunkedDownloader

logger = logging.getLogger("aae.internet_archive")

BOT_USER_AGENT = "agent-acquisition-engine/0.2.0 (+https://github.com/rc710056/agent-acquisition-engine; bot)"

MEDIA_EXTENSIONS: Dict[str, tuple[str, str, Optional[bool], Optional[bool]]] = {
    # Video: file_type, mime_type, has_video, has_audio
    "mp4": ("video", "video/mp4", True, True),
    "mkv": ("video", "video/x-matroska", True, True),
    "webm": ("video", "video/webm", True, True),
    "avi": ("video", "video/x-msvideo", True, True),
    "mov": ("video", "video/quicktime", True, True),
    "flv": ("video", "video/x-flv", True, True),
    "ogv": ("video", "video/ogg", True, True),
    "m4v": ("video", "video/x-m4v", True, True),
    # Audio
    "mp3": ("audio", "audio/mpeg", False, True),
    "flac": ("audio", "audio/flac", False, True),
    "wav": ("audio", "audio/wav", False, True),
    "ogg": ("audio", "audio/ogg", False, True),
    "m4a": ("audio", "audio/mp4", False, True),
    "wma": ("audio", "audio/x-ms-wma", False, True),
    "aac": ("audio", "audio/aac", False, True),
    # Documents
    "pdf": ("document", "application/pdf", False, False),
    "epub": ("document", "application/epub+zip", False, False),
    "txt": ("document", "text/plain", False, False),
    "djvu": ("document", "image/vnd.djvu", False, False),
    "cbz": ("document", "application/vnd.comicbook+zip", False, False),
    "cbr": ("document", "application/vnd.comicbook-rar", False, False),
    # Archives
    "zip": ("archive", "application/zip", False, False),
    "tar": ("archive", "application/x-tar", False, False),
    "gz": ("archive", "application/gzip", False, False),
    "7z": ("archive", "application/x-7z-compressed", False, False),
    "iso": ("archive", "application/x-iso9660-image", False, False),
    # Images
    "png": ("image", "image/png", False, False),
    "jpg": ("image", "image/jpeg", False, False),
    "jpeg": ("image", "image/jpeg", False, False),
    "webp": ("image", "image/webp", False, False),
}

def extract_ia_identifier_and_file(url: str) -> tuple[Optional[str], Optional[str]]:
    parsed = urlparse(url.strip())
    path = parsed.path.strip("/")
    parts = [p for p in path.split("/") if p]
    if not parts:
        return None, None

    first = parts[0].lower()
    if first in ("details", "metadata", "stream", "embed", "download"):
        identifier = parts[1] if len(parts) > 1 else None
        target_file = "/".join(parts[2:]) if len(parts) > 2 else None
        return identifier, target_file
    else:
        reserved = {"about", "contact", "donate", "terms", "services", "developers", "create", "account", "login", "search"}
        if first not in reserved:
            identifier = parts[0]
            target_file = "/".join(parts[1:]) if len(parts) > 1 else None
            return identifier, target_file
    return None, None

class InternetArchiveProvider(BaseProviderContract):
    """
    Internet Archive (archive.org) provider for Agent Acquisition Engine.
    Extracts structured metadata and file catalogs from https://archive.org/metadata/{identifier},
    maps all available open media streams (video, audio, text/pdf, archives) with actual sizes
    and direct download URLs https://archive.org/download/{identifier}/{file}.
    """

    @property
    def provider_id(self) -> str:
        return "internet_archive"

    @property
    def display_name(self) -> str:
        return "Internet Archive Provider"

    def can_handle(self, url: str) -> bool:
        if not url:
            return False
        clean = url.strip().lower()
        if clean.startswith("https://archive.org") or clean.startswith("http://archive.org"):
            return True
        parsed = urlparse(clean)
        netloc = parsed.netloc.split(":")[0]
        return netloc == "archive.org" or netloc.endswith(".archive.org")

    async def inspect(self, url: str) -> SourceInspectionResponse:
        clean_url = url.strip()
        is_safe, error = SSRFValidator.validate_url(clean_url)
        if not is_safe:
            return SourceInspectionResponse(
                source_id=f"src_{uuid.uuid4().hex[:12]}",
                url=clean_url,
                resolved_url=clean_url,
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

        identifier, target_file = extract_ia_identifier_and_file(clean_url)
        if not identifier:
            return SourceInspectionResponse(
                source_id=f"src_{uuid.uuid4().hex[:12]}",
                url=clean_url,
                resolved_url=clean_url,
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
                errors=["Could not extract an item identifier from the Internet Archive URL."]
            )

        meta_endpoint = f"https://archive.org/metadata/{identifier}"
        is_safe, error = SSRFValidator.validate_url(meta_endpoint)
        if not is_safe:
            return SourceInspectionResponse(
                source_id=f"src_{uuid.uuid4().hex[:12]}",
                url=clean_url,
                resolved_url=clean_url,
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
                errors=[error or "SSRF check failed on metadata endpoint."]
            )

        headers = {
            "User-Agent": BOT_USER_AGENT,
            "Accept": "application/json, text/plain, */*"
        }

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(meta_endpoint, headers=headers)
                if resp.status_code in {403, 429, 503}:
                    return SourceInspectionResponse(
                        source_id=f"src_{uuid.uuid4().hex[:12]}",
                        url=clean_url,
                        resolved_url=str(resp.url),
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
                        errors=[f"Internet Archive returned HTTP {resp.status_code}: Access blocked or rate limited."]
                    )

                if resp.status_code >= 400:
                    return SourceInspectionResponse(
                        source_id=f"src_{uuid.uuid4().hex[:12]}",
                        url=clean_url,
                        resolved_url=str(resp.url),
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
                        errors=[f"Internet Archive metadata query failed with HTTP {resp.status_code}."]
                    )

                data = resp.json()
        except Exception as e:
            return SourceInspectionResponse(
                source_id=f"src_{uuid.uuid4().hex[:12]}",
                url=clean_url,
                resolved_url=clean_url,
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
                errors=[f"Failed to fetch Internet Archive metadata: {str(e)}"]
            )

        meta = data.get("metadata", {}) or {}
        title = meta.get("title") or identifier
        description = meta.get("description")
        date = meta.get("date") or meta.get("year")
        creator = meta.get("creator")
        files = data.get("files", []) or []

        if not files:
            return SourceInspectionResponse(
                source_id=f"src_{uuid.uuid4().hex[:12]}",
                url=clean_url,
                resolved_url=f"https://archive.org/details/{identifier}",
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
                title=f"Internet Archive: {title}",
                errors=[f"No files discovered for item '{identifier}'."]
            )

        formats: List[FormatOption] = []
        assets: List[MediaAsset] = []
        recommended_format: Optional[FormatOption] = None
        total_estimated_size = 0

        # Sort files: if target_file is requested, put it first. Then video, audio, documents, others.
        for f in files:
            filename = f.get("name", "")
            if not filename or filename.startswith(".") or filename.endswith(("_meta.xml", "_meta.sqlite", "_files.xml", "_reviews.xml", "_archive.torrent")):
                continue

            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            if ext not in MEDIA_EXTENSIONS:
                continue

            file_type, mime_type, has_video, has_audio = MEDIA_EXTENSIONS[ext]
            size_val = f.get("size")
            size_bytes = int(size_val) if size_val and str(size_val).isdigit() else None
            if size_bytes:
                total_estimated_size += size_bytes

            file_format = f.get("format") or ext.upper()
            dl_url = f"https://archive.org/download/{identifier}/{filename}"
            clean_fid = re.sub(r'[^a-zA-Z0-9_\-]', '_', filename)
            format_id = f"ia_{clean_fid}"

            quality_label = f"{file_format}: {filename}"
            if size_bytes:
                quality_label += f" ({size_bytes / (1024 * 1024):.1f} MB)"

            is_match = False
            if target_file and (filename.lower() == target_file.lower() or filename.lower().endswith(target_file.lower())):
                is_match = True

            cat = "recommended" if is_match else ("video" if file_type == "video" else ("audio_only" if file_type == "audio" else "document"))

            option = FormatOption(
                format_id=format_id,
                file_type=file_type,
                mime_type=mime_type,
                resolution=None,
                codec=None,
                estimated_size_bytes=size_bytes,
                quality_label=quality_label,
                download_url=dl_url,
                has_audio=has_audio,
                has_video=has_video,
                category=cat
            )

            if is_match and not recommended_format:
                recommended_format = option

            formats.append(option)

        if not formats:
            return SourceInspectionResponse(
                source_id=f"src_{uuid.uuid4().hex[:12]}",
                url=clean_url,
                resolved_url=f"https://archive.org/details/{identifier}",
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
                title=f"Internet Archive: {title}",
                errors=[f"No downloadable media formats discovered for item '{identifier}'."]
            )

        # Pick recommended format if none was explicitly matched
        if not recommended_format:
            # Prefer mp4/mkv video
            for fmt in formats:
                if fmt.file_type == "video" and fmt.mime_type in ("video/mp4", "video/x-matroska"):
                    recommended_format = fmt
                    break
            # Fallback to any video
            if not recommended_format:
                for fmt in formats:
                    if fmt.file_type == "video":
                        recommended_format = fmt
                        break
            # Fallback to audio
            if not recommended_format:
                for fmt in formats:
                    if fmt.file_type == "audio":
                        recommended_format = fmt
                        break
            # Fallback to first format
            if not recommended_format:
                recommended_format = formats[0]

        # Prioritize recommended format at index 0 and mark category
        if recommended_format:
            recommended_format.category = "recommended"
            formats.remove(recommended_format)
            formats.insert(0, recommended_format)

        thumbnail_url = f"https://archive.org/services/img/{identifier}"

        primary_asset = MediaAsset(
            asset_id=f"ia_{identifier[:12]}",
            asset_type=recommended_format.file_type if recommended_format else "video",
            title=str(title),
            url=f"https://archive.org/details/{identifier}",
            thumbnail_url=thumbnail_url,
            mime_type=recommended_format.mime_type if recommended_format else "video/mp4",
            synopsis=str(description) if description else None,
            year=str(date) if date else None
        )
        assets.append(primary_asset)

        return SourceInspectionResponse(
            source_id=f"src_{uuid.uuid4().hex[:12]}",
            url=clean_url,
            resolved_url=f"https://archive.org/details/{identifier}",
            source_type=SourceType.MEDIA_COLLECTION,
            provider_id=self.provider_id,
            is_permitted=True,
            security_status=SecurityStatus.SAFE,
            acquisition_permission=AcquisitionPermission.PERMITTED,
            source_access_status=SourceAccessStatus.ACCESSIBLE,
            capabilities=["direct_stream", "archive_org_metadata", "chunked_download", "resume"],
            mime_type=recommended_format.mime_type if recommended_format else "video/mp4",
            estimated_size_bytes=recommended_format.estimated_size_bytes if recommended_format else None,
            inspection_status="inspected",
            title=f"Internet Archive: {title}",
            thumbnail_url=thumbnail_url,
            assets=assets,
            formats=formats,
            errors=[]
        )

    async def list_formats(self, url: str) -> List[FormatOption]:
        inspection = await self.inspect(url)
        return inspection.formats or []

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

        inspection = await self.inspect(url)
        if not inspection.is_permitted or not inspection.formats:
            err_msg = "; ".join(inspection.errors) if inspection.errors else "No valid formats available."
            raise RuntimeError(f"Cannot acquire source: {err_msg}")

        chosen_format: Optional[FormatOption] = None
        for fmt in inspection.formats:
            if fmt.format_id == format_id or fmt.format_id == f"ia_{format_id}":
                chosen_format = fmt
                break

        if not chosen_format:
            # Fallback to recommended or first format
            chosen_format = inspection.formats[0]

        target_dl_url = chosen_format.download_url
        if not target_dl_url:
            raise RuntimeError(f"Format {format_id} does not have a valid download URL.")

        filename = os.path.basename(urlparse(target_dl_url).path) or f"{chosen_format.format_id}.bin"
        filename = sanitize_filename(filename)

        headers = {
            "User-Agent": BOT_USER_AGENT,
            "Accept": "*/*",
            "Accept-Encoding": "identity"
        }

        downloader = ChunkedDownloader(concurrency=4)
        dl_res = await downloader.download(
            url=target_dl_url,
            destination_path=destination_path,
            total_bytes=chosen_format.estimated_size_bytes,
            headers=headers,
            progress_callback=progress_callback,
            timeout_seconds=timeout_seconds,
            max_size_bytes=max_size_bytes
        )

        return {
            "filename": filename,
            "mime_type": chosen_format.mime_type,
            "transferred_bytes": dl_res["bytes_downloaded"],
            "total_bytes": chosen_format.estimated_size_bytes or dl_res["bytes_downloaded"],
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
