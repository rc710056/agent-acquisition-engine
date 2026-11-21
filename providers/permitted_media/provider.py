import os
import re
import uuid
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Awaitable
from urllib.parse import urlparse
import httpx

from packages.provider_contracts.base import BaseProviderContract
from packages.shared_schemas.models import (
    FormatOption,
    SourceInspectionResponse,
    SourceType,
    SecurityStatus,
    AcquisitionPermission,
    SourceAccessStatus,
    MediaAsset
)
from apps.api.app.security.ssrf import SSRFValidator
from apps.api.app.security.sanitization import sanitize_filename
from apps.api.app.services.verification import FileVerifier, VerificationResult

class PermittedMediaProvider(BaseProviderContract):
    """
    Acquisition provider for authorized media platforms and webpages with embedded media.
    Uses yt-dlp metadata extraction and direct stream discovery.
    """

    @property
    def provider_id(self) -> str:
        return "permitted_media"

    @property
    def display_name(self) -> str:
        return "Permitted Media Provider (yt-dlp / Embedded Media)"

    def can_handle(self, url: str) -> bool:
        if not url:
            return False
        netloc = urlparse(url).netloc.lower()
        media_domains = [
            "youtube.com", "youtu.be", "vimeo.com", "reddit.com", "v.redd.it",
            "soundcloud.com", "bandcamp.com", "dailymotion.com"
        ]
        return any(d in netloc for d in media_domains)

    async def inspect(self, url: str) -> SourceInspectionResponse:
        is_safe, error = SSRFValidator.validate_url(url)
        if not is_safe:
            return SourceInspectionResponse(
                source_id=f"src_{uuid.uuid4().hex[:12]}",
                url=url,
                resolved_url=url,
                source_type=SourceType.PLATFORM_MEDIA_PAGE,
                provider_id=self.provider_id,
                is_permitted=False,
                security_status=SecurityStatus.BLOCKED,
                acquisition_permission=AcquisitionPermission.RESTRICTED,
                source_access_status=SourceAccessStatus.BLOCKED,
                capabilities=[],
                inspection_status="failed",
                errors=[error or "SSRF check failed."]
            )

        formats: List[FormatOption] = []
        assets: List[MediaAsset] = []
        title: Optional[str] = None
        thumbnail_url: Optional[str] = None
        duration: Optional[float] = None
        resolved_url = url
        primary_mime = "video/mp4"

        try:
            import yt_dlp
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": False,
                "skip_download": True
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    title = info.get("title")
                    thumbnail_url = info.get("thumbnail")
                    duration = info.get("duration")
                    resolved_url = info.get("webpage_url") or url

                    raw_formats = info.get("formats", [])
                    seen_formats = set()

                    for f in raw_formats:
                        fmt_id = f.get("format_id")
                        vcodec = f.get("vcodec")
                        acodec = f.get("acodec")
                        ext = f.get("ext", "mp4")
                        res = f.get("resolution") or (f"{f.get('width')}x{f.get('height')}" if f.get("width") else None)
                        f_url = f.get("url")

                        if vcodec == "none" and acodec == "none":
                            continue

                        filesize = f.get("filesize") or f.get("filesize_approx")
                        height = f.get("height")
                        label = f"{height}p ({ext})" if height else f"{fmt_id} ({ext})"

                        if label in seen_formats:
                            continue
                        seen_formats.add(label)

                        file_type = "video" if vcodec != "none" else "audio"
                        mime = f"{file_type}/{ext}" if ext in {"mp4", "webm", "mp3", "m4a", "ogg"} else f"{file_type}/mp4"

                        formats.append(FormatOption(
                            format_id=fmt_id,
                            file_type=file_type,
                            mime_type=mime,
                            resolution=res,
                            codec=f"{vcodec}/{acodec}" if vcodec else acodec,
                            estimated_size_bytes=filesize,
                            quality_label=label,
                            download_url=f_url
                        ))

                    if formats:
                        assets.append(MediaAsset(
                            asset_id="primary_media",
                            asset_type="video" if any(f.file_type == "video" for f in formats) else "audio",
                            title=title,
                            url=resolved_url,
                            thumbnail_url=thumbnail_url,
                            duration_seconds=float(duration) if duration else None,
                            mime_type=formats[0].mime_type
                        ))
        except Exception as e:
            # Check if this is an embedded webpage with video tags
            pass

        # Fallback inspection for HTML page with embedded media
        if not formats:
            try:
                headers = {"User-Agent": "Mozilla/5.0"}
                async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                    resp = await client.get(url, headers=headers)
                    resolved_url = str(resp.url)
                    html = resp.text

                    # Extract video sources
                    video_srcs = re.findall(r'<video[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
                    source_srcs = re.findall(r'<source[^>]+src=["\']([^"\']+)["\'][^>]*type=["\']video/([^"\']+)["\']', html, re.IGNORECASE)

                    for idx, v_url in enumerate(video_srcs):
                        from urllib.parse import urljoin
                        full_v_url = urljoin(resolved_url, v_url)
                        formats.append(FormatOption(
                            format_id=f"embedded_video_{idx+1}",
                            file_type="video",
                            mime_type="video/mp4",
                            resolution=None,
                            codec=None,
                            estimated_size_bytes=None,
                            quality_label=f"Embedded Video {idx+1}",
                            download_url=full_v_url
                        ))

                    for idx, (s_url, s_type) in enumerate(source_srcs):
                        from urllib.parse import urljoin
                        full_s_url = urljoin(resolved_url, s_url)
                        formats.append(FormatOption(
                            format_id=f"embedded_source_{idx+1}",
                            file_type="video",
                            mime_type=f"video/{s_type}",
                            resolution=None,
                            codec=None,
                            estimated_size_bytes=None,
                            quality_label=f"Source Stream {idx+1} ({s_type})",
                            download_url=full_s_url
                        ))
            except Exception:
                pass

        if not formats:
            return SourceInspectionResponse(
                source_id=f"src_{uuid.uuid4().hex[:12]}",
                url=url,
                resolved_url=resolved_url,
                source_type=SourceType.UNSUPPORTED_SOURCE,
                provider_id=self.provider_id,
                is_permitted=False,
                security_status=SecurityStatus.SAFE,
                acquisition_permission=AcquisitionPermission.RESTRICTED,
                source_access_status=SourceAccessStatus.ACCESSIBLE,
                capabilities=[],
                inspection_status="failed",
                errors=["No extractable media streams found on target platform or page."]
            )

        return SourceInspectionResponse(
            source_id=f"src_{uuid.uuid4().hex[:12]}",
            url=url,
            resolved_url=resolved_url,
            source_type=SourceType.PLATFORM_MEDIA_PAGE if self.can_handle(url) else SourceType.WEBPAGE_WITH_MEDIA,
            provider_id=self.provider_id,
            is_permitted=True,
            security_status=SecurityStatus.SAFE,
            acquisition_permission=AcquisitionPermission.PERMITTED,
            source_access_status=SourceAccessStatus.ACCESSIBLE,
            capabilities=["media_extraction", "stream_download"],
            mime_type=formats[0].mime_type if formats else primary_mime,
            estimated_size_bytes=formats[0].estimated_size_bytes if formats else None,
            inspection_status="inspected",
            title=title or "Permitted Media Source",
            thumbnail_url=thumbnail_url,
            assets=assets,
            formats=formats,
            errors=[]
        )

    async def list_formats(self, url: str) -> List[FormatOption]:
        inspection = await self.inspect(url)
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
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        inspection = await self.inspect(url)
        if not inspection.is_permitted or not inspection.formats:
            raise ValueError(f"Cannot acquire media: {'; '.join(inspection.errors) or 'No formats available.'}")

        target_format = next((f for f in inspection.formats if f.format_id == format_id), inspection.formats[0])
        direct_url = target_format.download_url or url

        sha256 = hashlib.sha256()
        transferred_bytes = 0
        total_bytes: Optional[int] = None
        ext = target_format.mime_type.split("/")[-1] if "/" in target_format.mime_type else "mp4"
        extracted_filename = f"media_{uuid.uuid4().hex[:8]}.{ext}"

        headers = {"User-Agent": "Mozilla/5.0"}
        async with httpx.AsyncClient(timeout=float(timeout_seconds), follow_redirects=True) as client:
            async with client.stream("GET", direct_url, headers=headers) as response:
                if response.status_code >= 400:
                    raise RuntimeError(f"Media stream failed with HTTP status {response.status_code}")

                resp_mime = response.headers.get("content-type", "").lower()
                if "text/html" in resp_mime and target_format.file_type in {"video", "audio"}:
                    raise RuntimeError(f"Expected media stream but received HTML webpage ({resp_mime}).")

                cl = response.headers.get("content-length")
                if cl and cl.isdigit():
                    total_bytes = int(cl)
                    if total_bytes > max_size_bytes:
                        raise ValueError(f"Resource size exceeds maximum limit of {max_size_bytes} bytes")

                with open(destination_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        if not chunk:
                            continue
                        transferred_bytes += len(chunk)
                        if transferred_bytes > max_size_bytes:
                            raise ValueError(f"Download exceeded limit of {max_size_bytes} bytes")

                        sha256.update(chunk)
                        f.write(chunk)

                        if progress_callback:
                            await progress_callback(transferred_bytes, total_bytes)

        return {
            "filename": extracted_filename,
            "mime_type": target_format.mime_type,
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
