import os
import re
import uuid
import json
import hashlib
import asyncio
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

class CobaltProvider(BaseProviderContract):
    """
    Cobalt Universal Media Adapter.
    Acts as a high-speed fallback provider for social media platforms (Twitter/X,
    TikTok, Instagram, Reddit, YouTube, SoundCloud) when direct scrapers encounter
    anti-bot defenses, IP rate limits, or JS challenge walls.
    Integrates with self-hosted Cobalt instances or configured microservice endpoints.
    """

    COBALT_DOMAINS = [
        "twitter.com", "x.com", "tiktok.com", "instagram.com", "threads.net",
        "youtube.com", "youtu.be", "reddit.com", "v.redd.it", "soundcloud.com",
        "bilibili.com", "vimeo.com", "vk.com", "dailymotion.com", "tumblr.com",
        "pinterest.com", "pin.it"
    ]

    def __init__(self, api_url: Optional[str] = None):
        self.api_url = (api_url or os.environ.get("COBALT_API_URL", "http://127.0.0.1:9000")).rstrip("/")

    @property
    def provider_id(self) -> str:
        return "cobalt"

    @property
    def display_name(self) -> str:
        return "Cobalt Universal Media Adapter (Anti-Bot Resilience)"

    def can_handle(self, url: str) -> bool:
        if not url:
            return False
        netloc = urlparse(url).netloc.lower()
        return any(d in netloc for d in self.COBALT_DOMAINS)

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

        formats = [
            FormatOption(
                format_id="cobalt_best_video",
                file_type="video",
                mime_type="video/mp4",
                resolution="1920x1080",
                codec="h264+aac",
                estimated_size_bytes=None,
                quality_label="★ Cobalt Resilient Stream (Best Quality 1080p Full HD) • with Audio",
                category="recommended",
                has_audio=True,
                has_video=True
            ),
            FormatOption(
                format_id="cobalt_audio",
                file_type="audio",
                mime_type="audio/mpeg",
                resolution=None,
                codec="mp3",
                estimated_size_bytes=None,
                quality_label="Cobalt High-Fidelity Audio Track (MP3 320k)",
                category="audio_only",
                has_audio=True,
                has_video=False
            )
        ]

        return SourceInspectionResponse(
            source_id=f"src_{uuid.uuid4().hex[:12]}",
            url=url,
            resolved_url=url,
            source_type=SourceType.PLATFORM_MEDIA_PAGE,
            provider_id=self.provider_id,
            is_permitted=True,
            security_status=SecurityStatus.SAFE,
            acquisition_permission=AcquisitionPermission.PERMITTED,
            source_access_status=SourceAccessStatus.ACCESSIBLE,
            capabilities=["resilient_stream", "anti_bot_fallback", "multiplexed_download"],
            mime_type="video/mp4",
            estimated_size_bytes=None,
            inspection_status="inspected",
            title=f"Media via Cobalt ({urlparse(url).netloc})",
            thumbnail_url=None,
            formats=formats,
            assets=[],
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
            raise ValueError(f"SSRF check failed: {error}")

        is_audio = ("audio" in format_id) and ("video" not in format_id)
        payload = {
            "url": url,
            "videoQuality": "1080",
            "audioFormat": "mp3",
            "downloadMode": "audio" if is_audio else "auto"
        }

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "AgentAcquisitionEngine/0.1.0"
        }

        # Try API v10 endpoint first, fallback to v7 /api/json
        endpoints = [f"{self.api_url}/", f"{self.api_url}/api/json"]
        cobalt_data = None
        last_err = None

        async with httpx.AsyncClient(timeout=30.0) as client:
            for ep in endpoints:
                try:
                    resp = await client.post(ep, json=payload, headers=headers)
                    if resp.status_code in (200, 201):
                        cobalt_data = resp.json()
                        break
                    else:
                        last_err = f"Cobalt returned HTTP {resp.status_code}: {resp.text}"
                except Exception as e:
                    last_err = str(e)

        if not cobalt_data:
            raise RuntimeError(f"Cobalt acquisition request failed across endpoints: {last_err}")

        status = cobalt_data.get("status")
        stream_url = cobalt_data.get("url")

        if status == "picker":
            picker_items = cobalt_data.get("picker", [])
            if picker_items:
                stream_url = picker_items[0].get("url")

        if not stream_url or status == "error":
            err_msg = cobalt_data.get("text") or "No downloadable stream URL returned by Cobalt."
            raise RuntimeError(f"Cobalt returned error status: {err_msg}")

        # Stream download file from Cobalt stream URL
        ext = "mp3" if is_audio else "mp4"
        final_filename = cobalt_data.get("filename") or f"media_{uuid.uuid4().hex[:8]}.{ext}"
        final_filename = sanitize_filename(final_filename)

        sha256 = hashlib.sha256()
        bytes_transferred = 0

        async with httpx.AsyncClient(timeout=float(timeout_seconds), follow_redirects=True) as stream_client:
            async with stream_client.stream("GET", stream_url) as stream_resp:
                if stream_resp.status_code >= 400:
                    raise RuntimeError(f"Failed to stream media from Cobalt link: HTTP {stream_resp.status_code}")

                total_header = stream_resp.headers.get("Content-Length")
                total_bytes = int(total_header) if total_header and total_header.isdigit() else None

                with open(destination_path, "wb") as f:
                    async for chunk in stream_resp.aiter_bytes(chunk_size=65536):
                        f.write(chunk)
                        sha256.update(chunk)
                        bytes_transferred += len(chunk)

                        if bytes_transferred > max_size_bytes:
                            destination_path.unlink(missing_ok=True)
                            raise ValueError(f"Acquired media size ({bytes_transferred} bytes) exceeds limit ({max_size_bytes} bytes)")

                        if progress_callback:
                            await progress_callback(bytes_transferred, total_bytes)

        detected_mime = "audio/mpeg" if is_audio else "video/mp4"

        return {
            "filename": final_filename,
            "mime_type": detected_mime,
            "size_bytes": bytes_transferred,
            "total_bytes": bytes_transferred,
            "sha256": sha256.hexdigest(),
            "provider": self.provider_id
        }

    def verify(
        self,
        file_path: Path,
        expected_size: Optional[int] = None,
        expected_sha256: Optional[str] = None,
        expected_mime: Optional[str] = None,
        expected_file_type: Optional[str] = None,
        **kwargs
    ) -> VerificationResult:
        return FileVerifier.verify_file(
            file_path,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
            expected_mime=expected_mime,
            expected_file_type=expected_file_type
        )
