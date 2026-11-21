import os
import sys
import re
import uuid
import json
import zipfile
import hashlib
import asyncio
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Awaitable
from urllib.parse import urlparse

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

class GalleryDLProvider(BaseProviderContract):
    """
    Dedicated acquisition provider for image galleries, carousels, photo albums,
    and multi-image posts using gallery-dl.
    Supports Imgur, Reddit galleries, Instagram carousels, Pinterest boards, DeviantArt, etc.
    Acquires collections as sanitized .zip archives or individual cover images.
    """

    @property
    def provider_id(self) -> str:
        return "gallery_dl"

    @property
    def display_name(self) -> str:
        return "Gallery & Image Collection Provider (gallery-dl)"

    def can_handle(self, url: str) -> bool:
        if not url:
            return False
        netloc = urlparse(url).netloc.lower()
        # Avoid YouTube/Vimeo video streaming platforms that belong strictly to permitted_media
        if any(d in netloc for d in ["youtube.com", "youtu.be", "vimeo.com"]):
            return False

        try:
            from gallery_dl import extractor
            ext = extractor.find(url)
            return ext is not None
        except Exception:
            # Fallback domain check
            gallery_domains = [
                "imgur.com", "reddit.com", "redd.it", "deviantart.com",
                "artstation.com", "flickr.com", "unsplash.com", "pixiv.net"
            ]
            return any(d in netloc for d in gallery_domains)

    async def inspect(self, url: str) -> SourceInspectionResponse:
        is_safe, error = SSRFValidator.validate_url(url)
        if not is_safe:
            return SourceInspectionResponse(
                source_id=f"src_{uuid.uuid4().hex[:12]}",
                url=url,
                resolved_url=url,
                source_type=SourceType.MEDIA_COLLECTION,
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

        loop = asyncio.get_running_loop()

        def _simulate_info():
            cmd = [
                sys.executable, "-m", "gallery_dl",
                "-j",
                "--range", "1-10",
                url
            ]
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=12.0)
                if proc.returncode == 0 and proc.stdout.strip():
                    results = []
                    for line in proc.stdout.strip().splitlines():
                        try:
                            item = json.loads(line)
                            # gallery-dl JSON output format: [type_id, data]
                            if isinstance(item, list) and len(item) > 1:
                                results.append(item[1])
                            elif isinstance(item, dict):
                                results.append(item)
                        except Exception:
                            continue
                    return results
            except Exception:
                pass
            return []

        extracted_items = await loop.run_in_executor(None, _simulate_info)

        item_count = len(extracted_items)
        if extracted_items:
            first = extracted_items[0]
            title = first.get("title") or first.get("description") or f"Image Collection ({item_count} items)"
            thumbnail_url = first.get("thumbnail") or first.get("url")

            for idx, item in enumerate(extracted_items[:10]):
                item_url = item.get("url")
                if item_url:
                    assets.append(MediaAsset(
                        asset_id=f"item_{idx+1}",
                        asset_type="image",
                        title=item.get("filename") or f"Image #{idx+1}",
                        url=item_url,
                        thumbnail_url=item.get("thumbnail") or item_url,
                        mime_type="image/jpeg"
                    ))

        # Always present complete archive zip and single cover image
        formats.append(FormatOption(
            format_id="all_images_zip",
            file_type="archive",
            mime_type="application/zip",
            resolution=None,
            codec=None,
            estimated_size_bytes=None,
            quality_label=f"★ Complete Gallery Archive (.zip) • All High-Res Images ({item_count} items)" if item_count else "★ Complete Gallery Archive (.zip)",
            category="recommended",
            has_audio=False,
            has_video=False
        ))

        formats.append(FormatOption(
            format_id="first_image",
            file_type="image",
            mime_type="image/jpeg",
            resolution=None,
            codec=None,
            estimated_size_bytes=None,
            quality_label="Primary / Cover Image Only (.jpg)",
            category="single_image",
            has_audio=False,
            has_video=False
        ))

        return SourceInspectionResponse(
            source_id=f"src_{uuid.uuid4().hex[:12]}",
            url=url,
            resolved_url=url,
            source_type=SourceType.MEDIA_COLLECTION,
            provider_id=self.provider_id,
            is_permitted=True,
            security_status=SecurityStatus.SAFE,
            acquisition_permission=AcquisitionPermission.PERMITTED,
            source_access_status=SourceAccessStatus.ACCESSIBLE,
            capabilities=["gallery_archive", "multi_image_extraction", "direct_download"],
            mime_type="application/zip",
            estimated_size_bytes=None,
            inspection_status="inspected",
            title=title or "Image Gallery Collection",
            thumbnail_url=thumbnail_url,
            formats=formats,
            assets=assets,
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
        is_safe, error = SSRFValidator.validate_url(url)
        if not is_safe:
            raise ValueError(f"SSRF violation: {error}")

        loop = asyncio.get_running_loop()
        temp_dir = destination_path.parent / f"gdl_{uuid.uuid4().hex[:8]}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            def _run_gallery_dl():
                cmd = [
                    sys.executable, "-m", "gallery_dl",
                    "--dest", str(temp_dir),
                    "--range", "1-50",
                    url
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds)
                return proc.returncode

            returncode = await loop.run_in_executor(None, _run_gallery_dl)

            # Discover all downloaded image files in temp_dir
            downloaded_files = [f for f in temp_dir.rglob("*") if f.is_file()]
            if not downloaded_files:
                raise RuntimeError("gallery-dl completed but no image files were acquired.")

            if format_id == "first_image":
                # Extract first image file
                first_file = downloaded_files[0]
                ext = first_file.suffix or ".jpg"
                if destination_path.exists():
                    destination_path.unlink()
                first_file.rename(destination_path)
                final_filename = f"image_{uuid.uuid4().hex[:8]}{ext}"
                final_mime = "image/png" if ext == ".png" else "image/jpeg"
            else:
                # Pack all files into a sanitized zip archive
                if destination_path.exists():
                    destination_path.unlink()
                with zipfile.ZipFile(destination_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for f in downloaded_files:
                        arcname = sanitize_filename(f.name)
                        zf.write(f, arcname=arcname)
                final_filename = f"gallery_{uuid.uuid4().hex[:8]}.zip"
                final_mime = "application/zip"

            file_size = destination_path.stat().st_size
            if file_size > max_size_bytes:
                destination_path.unlink(missing_ok=True)
                raise ValueError(f"Acquired gallery archive ({file_size} bytes) exceeds limit ({max_size_bytes} bytes)")

            sha256 = hashlib.sha256()
            with open(destination_path, "rb") as f:
                while chunk := f.read(65536):
                    sha256.update(chunk)

            if progress_callback:
                await progress_callback(file_size, file_size)

            return {
                "filename": final_filename,
                "mime_type": final_mime,
                "size_bytes": file_size,
                "total_bytes": file_size,
                "sha256": sha256.hexdigest(),
                "provider": self.provider_id
            }

        finally:
            # Clean up temporary downloaded files
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

    def verify(
        self,
        file_path: Path,
        expected_size: Optional[int] = None,
        expected_sha256: Optional[str] = None,
        expected_mime: Optional[str] = None
    ) -> VerificationResult:
        return FileVerifier.verify_file(
            file_path,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
            expected_mime=expected_mime
        )
