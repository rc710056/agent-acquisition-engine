import os
import re
import uuid
import json
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Awaitable
from urllib.parse import urlparse, unquote
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

class PinterestProvider(BaseProviderContract):
    """
    Dedicated acquisition provider for Pinterest media.
    Resolves short URLs (pin.it), inspects canonical pin pages, extracts real video
    and image assets using dual-mode extraction (yt-dlp and JSON-LD VideoObject parsing),
    and streams verified media files.
    """

    @property
    def provider_id(self) -> str:
        return "pinterest"

    @property
    def display_name(self) -> str:
        return "Pinterest Media Provider"

    def can_handle(self, url: str) -> bool:
        if not url:
            return False
        netloc = urlparse(url).netloc.lower()
        return any(domain in netloc for domain in ["pin.it", "pinterest.com", "pinimg.com"])

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

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"
        }

        # Step 1: Follow redirects to canonical URL and fetch page
        canonical_url = url
        html_body = ""
        status_code = 200

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                raw_redirect = str(resp.url)
                canonical_url = raw_redirect
                status_code = resp.status_code
                if status_code < 400:
                    html_body = resp.text

                # Extract true canonical pin URL from login redirect or tracking URLs
                pin_match = re.search(r'/pin/(\d+)', unquote(raw_redirect))
                if pin_match:
                    canonical_url = f"https://www.pinterest.com/pin/{pin_match.group(1)}/"
                    if "login/" in raw_redirect:
                        # Re-fetch canonical pin URL to retrieve page with video tags
                        pin_resp = await client.get(canonical_url, headers=headers)
                        if pin_resp.status_code < 400:
                            html_body = pin_resp.text
        except Exception as e:
            return SourceInspectionResponse(
                source_id=f"src_{uuid.uuid4().hex[:12]}",
                url=url,
                resolved_url=canonical_url,
                source_type=SourceType.PLATFORM_MEDIA_PAGE,
                provider_id=self.provider_id,
                is_permitted=False,
                security_status=SecurityStatus.SAFE,
                acquisition_permission=AcquisitionPermission.UNKNOWN,
                source_access_status=SourceAccessStatus.UNAVAILABLE,
                capabilities=[],
                inspection_status="failed",
                errors=[f"Failed to reach Pinterest source: {str(e)}"]
            )

        if status_code in {401, 403}:
            return SourceInspectionResponse(
                source_id=f"src_{uuid.uuid4().hex[:12]}",
                url=url,
                resolved_url=canonical_url,
                source_type=SourceType.PLATFORM_MEDIA_PAGE,
                provider_id=self.provider_id,
                is_permitted=False,
                security_status=SecurityStatus.SAFE,
                acquisition_permission=AcquisitionPermission.USER_AUTHORIZATION_REQUIRED,
                source_access_status=SourceAccessStatus.AUTHENTICATION_REQUIRED,
                capabilities=[],
                inspection_status="restricted",
                errors=[f"Pinterest returned HTTP {status_code}: Login or authorization required."]
            )

        # Step 2: Try yt-dlp extraction
        assets: List[MediaAsset] = []
        formats: List[FormatOption] = []
        title: Optional[str] = None
        thumbnail_url: Optional[str] = None
        primary_mime = "video/mp4"

        ytdl_success = False
        try:
            import yt_dlp
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": False,
                "skip_download": True
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(canonical_url, download=False)
                if info:
                    ytdl_success = True
                    title = info.get("title")
                    thumbnail_url = info.get("thumbnail")
                    duration = info.get("duration")

                    # Add video formats
                    raw_formats = info.get("formats", [])
                    seen_labels = set()
                    progressive_formats: List[FormatOption] = []
                    hls_formats: List[FormatOption] = []

                    for f in raw_formats:
                        fmt_id = f.get("format_id")
                        vcodec = f.get("vcodec")
                        res = f.get("resolution") or (f"{f.get('width')}x{f.get('height')}" if f.get("width") else None)
                        ext = f.get("ext", "mp4")
                        f_url = f.get("url", "")

                        # Skip audio-only streams for primary presentation unless requested
                        if vcodec == "none" or res == "audio only":
                            continue

                        is_hls = ".m3u8" in f_url or ext == "m3u8"
                        height = f.get("height", "video")
                        quality_label = f"{height}p (HLS)" if is_hls else f"{height}p (MP4)"
                        if quality_label in seen_labels:
                            quality_label = f"{quality_label}_{fmt_id}"
                        seen_labels.add(quality_label)

                        filesize = f.get("filesize") or f.get("filesize_approx")
                        mime = "application/vnd.apple.mpegurl" if is_hls else "video/mp4"

                        opt = FormatOption(
                            format_id=fmt_id or f"fmt_{len(formats)}",
                            file_type="video",
                            mime_type=mime,
                            resolution=res,
                            codec=vcodec,
                            estimated_size_bytes=filesize,
                            quality_label=quality_label,
                            download_url=f_url
                        )
                        if is_hls:
                            hls_formats.append(opt)
                        else:
                            progressive_formats.append(opt)

                    # Progressive standalone MP4 streams prioritized first
                    formats = progressive_formats + hls_formats

                    if formats:
                        assets.append(MediaAsset(
                            asset_id="pinterest_video",
                            asset_type="video",
                            title=title,
                            url=canonical_url,
                            thumbnail_url=thumbnail_url,
                            duration_seconds=float(duration) if duration else None,
                            mime_type="video/mp4"
                        ))
        except Exception:
            pass

        # Step 3: Supplemental/Fallback JSON-LD & DOM extraction
        if not formats and html_body:
            # Check for VideoObject
            video_obj_match = re.search(r'\{[^{}]*"@type"\s*:\s*"VideoObject"[^{}]*\}', html_body)
            if not video_obj_match:
                # Try multi-line JSON-LD scripts
                scripts = re.findall(r'<script[^>]*>(.*?)</script>', html_body, re.DOTALL)
                for s in scripts:
                    if "VideoObject" in s:
                        try:
                            v_data = json.loads(s)
                            if isinstance(v_data, dict) and v_data.get("@type") == "VideoObject":
                                content_url = v_data.get("contentUrl")
                                v_title = v_data.get("name")
                                v_thumb = v_data.get("thumbnailUrl")
                                width = v_data.get("width")
                                height = v_data.get("height")

                                title = title or v_title
                                thumbnail_url = thumbnail_url or v_thumb

                                if content_url:
                                    formats.append(FormatOption(
                                        format_id="original_video_720p",
                                        file_type="video",
                                        mime_type="video/mp4",
                                        resolution=f"{width}x{height}" if (width and height) else "720x1280",
                                        codec="h264",
                                        estimated_size_bytes=None,
                                        quality_label="720p (Original MP4)",
                                        download_url=content_url
                                    ))
                                    assets.append(MediaAsset(
                                        asset_id="pinterest_video",
                                        asset_type="video",
                                        title=title,
                                        url=content_url,
                                        thumbnail_url=thumbnail_url,
                                        mime_type="video/mp4"
                                    ))
                                break
                        except Exception:
                            continue

            # Check for high-res images if no video or in addition to video
            images = re.findall(r'https://i\.pinimg\.com/originals/[^\s"\'<>]+\.(?:jpg|png|webp)', html_body)
            if images:
                orig_img = list(set(images))[0]
                formats.append(FormatOption(
                    format_id="original_image",
                    file_type="image",
                    mime_type="image/jpeg",
                    resolution=None,
                    codec=None,
                    estimated_size_bytes=None,
                    quality_label="Original Image (High-Res)",
                    download_url=orig_img
                ))
                if not assets:
                    primary_mime = "image/jpeg"
                    assets.append(MediaAsset(
                        asset_id="pinterest_image",
                        asset_type="image",
                        title=title or "Pinterest Image",
                        url=orig_img,
                        mime_type="image/jpeg"
                    ))

        if not formats:
            return SourceInspectionResponse(
                source_id=f"src_{uuid.uuid4().hex[:12]}",
                url=url,
                resolved_url=canonical_url,
                source_type=SourceType.PLATFORM_MEDIA_PAGE,
                provider_id=self.provider_id,
                is_permitted=False,
                security_status=SecurityStatus.SAFE,
                acquisition_permission=AcquisitionPermission.RESTRICTED,
                source_access_status=SourceAccessStatus.ACCESSIBLE,
                capabilities=[],
                inspection_status="failed",
                errors=["No downloadable media stream or high-resolution asset found on this Pinterest pin."]
            )

        return SourceInspectionResponse(
            source_id=f"src_{uuid.uuid4().hex[:12]}",
            url=url,
            resolved_url=canonical_url,
            source_type=SourceType.PLATFORM_MEDIA_PAGE,
            provider_id=self.provider_id,
            is_permitted=True,
            security_status=SecurityStatus.SAFE,
            acquisition_permission=AcquisitionPermission.PERMITTED,
            source_access_status=SourceAccessStatus.ACCESSIBLE,
            capabilities=["stream_download", "multi_format", "video_inspection"],
            mime_type=primary_mime,
            estimated_size_bytes=formats[0].estimated_size_bytes if formats else None,
            inspection_status="inspected",
            title=title or "Pinterest Media Pin",
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
            raise ValueError(f"Cannot acquire Pinterest media: {'; '.join(inspection.errors) or 'No formats available.'}")

        # Find matching format option
        target_format = next((f for f in inspection.formats if f.format_id == format_id), None)
        if not target_format:
            target_format = inspection.formats[0]

        direct_download_url = target_format.download_url
        if not direct_download_url:
            # Fallback to resolved url
            direct_download_url = inspection.resolved_url or url

        # If an HLS manifest is targeted, prefer the direct progressive MP4 stream if available
        if ".m3u8" in direct_download_url:
            mp4_opt = next((f for f in inspection.formats if f.download_url and ".mp4" in f.download_url), None)
            if mp4_opt and mp4_opt.download_url:
                direct_download_url = mp4_opt.download_url
                target_format = mp4_opt

        # Stream directly
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        sha256 = hashlib.sha256()
        transferred_bytes = 0
        total_bytes: Optional[int] = None
        extracted_ext = "mp4" if target_format.file_type == "video" else "jpg"
        extracted_filename = f"pinterest_{uuid.uuid4().hex[:8]}.{extracted_ext}"

        async with httpx.AsyncClient(timeout=float(timeout_seconds), follow_redirects=True) as client:
            async with client.stream("GET", direct_download_url, headers=headers) as response:
                if response.status_code >= 400:
                    raise RuntimeError(f"HTTP stream failed with status {response.status_code}")

                # Ensure response is not an HTML error/login page
                resp_content_type = response.headers.get("content-type", "").lower()
                if "text/html" in resp_content_type and target_format.file_type in {"video", "image"}:
                    raise RuntimeError(f"Expected media stream but received HTML webpage ({resp_content_type}).")

                cl = response.headers.get("content-length")
                if cl and cl.isdigit():
                    total_bytes = int(cl)
                    if total_bytes > max_size_bytes:
                        raise ValueError(f"Resource size ({total_bytes} bytes) exceeds limit ({max_size_bytes} bytes)")

                with open(destination_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        if not chunk:
                            continue
                        transferred_bytes += len(chunk)
                        if transferred_bytes > max_size_bytes:
                            raise ValueError(f"Download exceeded maximum permitted size of {max_size_bytes} bytes")

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
