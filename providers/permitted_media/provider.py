import os
import re
import uuid
import asyncio
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

def get_friendly_resolution_name(height: int) -> str:
    if height >= 2160:
        return f"4K Ultra HD ({height}p)"
    elif height >= 1440:
        return f"2K Quad HD ({height}p)"
    elif height >= 1080:
        return f"Full HD ({height}p)"
    elif height >= 720:
        return f"HD ({height}p)"
    elif height >= 480:
        return f"SD ({height}p)"
    elif height >= 360:
        return f"Standard ({height}p)"
    return f"{height}p"

def clean_codec_name(c: Optional[str]) -> str:
    """Return normalized, honest codec name."""
    if not c or c.lower() == "none":
        return "unknown"
    c_low = c.lower().strip()
    if c_low.startswith("avc") or "h264" in c_low:
        return "h264"
    if c_low.startswith("vp09") or c_low.startswith("vp9"):
        return "vp9"
    if c_low.startswith("av01") or "av1" in c_low:
        return "av1"
    if c_low.startswith("mp4a") or "aac" in c_low:
        return "aac"
    if "opus" in c_low:
        return "opus"
    if "mp3" in c_low:
        return "mp3"
    return c_low.split(".")[0]

def estimate_stream_bytes(
    raw_format: Optional[dict] = None,
    duration_seconds: Optional[float] = None,
    default_kbps: int = 1500
) -> Optional[int]:
    """Estimate size in bytes from yt-dlp format dict or duration * bitrate."""
    if raw_format:
        filesize = raw_format.get("filesize")
        if filesize and isinstance(filesize, (int, float)) and filesize > 0:
            return int(filesize)
        filesize_approx = raw_format.get("filesize_approx")
        if filesize_approx and isinstance(filesize_approx, (int, float)) and filesize_approx > 0:
            return int(filesize_approx)
        tbr = raw_format.get("tbr") or (
            (raw_format.get("vbr") or 0) + (raw_format.get("abr") or 0)
        )
        if tbr and tbr > 0 and duration_seconds and duration_seconds > 0:
            return int((tbr * 1000 / 8) * duration_seconds)

    if duration_seconds and duration_seconds > 0 and default_kbps > 0:
        return int((default_kbps * 1000 / 8) * duration_seconds)

    return None

class PermittedMediaProvider(BaseProviderContract):
    """
    Acquisition provider for authorized media platforms (YouTube, Vimeo, Reddit, etc.)
    and generic webpages with embedded media.
    Discovers stream tracks, synthesizes high-quality Video+Audio presets,
    and multiplexes synchronized video+audio containers using ffmpeg.
    """

    @property
    def provider_id(self) -> str:
        return "permitted_media"

    @property
    def display_name(self) -> str:
        return "Permitted Media Provider (Muxed Video+Audio / yt-dlp)"

    def can_handle(self, url: str) -> bool:
        if not url:
            return False
        netloc = urlparse(url).netloc.lower()
        media_domains = [
            "youtube.com", "youtu.be", "vimeo.com", "reddit.com", "v.redd.it",
            "soundcloud.com", "bandcamp.com", "dailymotion.com",
            "instagram.com", "tiktok.com", "twitter.com", "x.com", "threads.net"
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
        has_video = False
        has_audio = False

        try:
            import yt_dlp
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": False,
                "skip_download": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    title = info.get("title")
                    thumbnail_url = info.get("thumbnail")
                    duration = info.get("duration")
                    resolved_url = info.get("webpage_url") or url

                    raw_formats = info.get("formats", [])
                    has_video = any(f.get("vcodec") and f.get("vcodec") != "none" for f in raw_formats)
                    has_audio = any(f.get("acodec") and f.get("acodec") != "none" for f in raw_formats)
                    video_formats = [f for f in raw_formats if f.get("vcodec") != "none"]
                    audio_formats = [f for f in raw_formats if f.get("acodec") and f.get("acodec") != "none"]

                    dur_sec = float(duration) if duration else None

                    # 1. Audio stream pairing
                    aac_audio_fmts = [
                        f for f in audio_formats
                        if f.get("acodec", "").startswith(("mp4a", "aac")) or "m4a" in f.get("ext", "")
                    ]
                    best_aac_audio = next(iter(sorted(
                        aac_audio_fmts,
                        key=lambda x: estimate_stream_bytes(x, dur_sec, default_kbps=128) or 0,
                        reverse=True
                    )), None)
                    best_any_audio = next(iter(sorted(
                        audio_formats,
                        key=lambda x: estimate_stream_bytes(x, dur_sec, default_kbps=160) or 0,
                        reverse=True
                    )), None)

                    audio_comp_bytes = estimate_stream_bytes(best_aac_audio or best_any_audio, dur_sec, default_kbps=128) or 0
                    audio_native_bytes = estimate_stream_bytes(best_any_audio, dur_sec, default_kbps=160) or 0
                    best_audio_bytes = audio_comp_bytes

                    if has_video:
                        # Find unique heights in ascending order for ladder calculations
                        heights_asc = sorted(list(set(f.get("height") for f in video_formats if f.get("height"))))

                        # Build compatible profile data for each height
                        height_comp_map = {}
                        for h in heights_asc:
                            h_fmts = [f for f in video_formats if f.get("height") == h]
                            h_avc = [f for f in h_fmts if f.get("vcodec", "").startswith(("avc", "h264"))]
                            best_h_avc = next(iter(sorted(
                                h_avc,
                                key=lambda x: estimate_stream_bytes(x, dur_sec, default_kbps=1000) or 0,
                                reverse=True
                            )), None)
                            best_h_any = next(iter(sorted(
                                h_fmts,
                                key=lambda x: estimate_stream_bytes(x, dur_sec, default_kbps=1000) or 0,
                                reverse=True
                            )), None)

                            chosen_fmt = best_h_avc or best_h_any
                            default_v = 4000 if h >= 1080 else (2500 if h >= 720 else (1200 if h >= 480 else (600 if h >= 360 else 350)))
                            v_bytes = estimate_stream_bytes(chosen_fmt, dur_sec, default_kbps=default_v) or 0
                            tot_bytes = v_bytes + audio_comp_bytes
                            height_comp_map[h] = {
                                "format": chosen_fmt,
                                "bytes": tot_bytes,
                                "is_h264": bool(best_h_avc is not None)
                            }

                        # Enforce strict monotonic ladder:
                        # Guarantees size(240p) < size(360p) < size(480p) < size(720p) < size(1080p)...
                        for idx in range(1, len(heights_asc)):
                            prev_h = heights_asc[idx - 1]
                            curr_h = heights_asc[idx]
                            if height_comp_map[curr_h]["bytes"] <= height_comp_map[prev_h]["bytes"]:
                                height_comp_map[curr_h]["bytes"] = int(height_comp_map[prev_h]["bytes"] * 1.15)

                        # Pick highest resolution fitting platform quota (<= 500 MB)
                        quota_limit = 524_288_000
                        acquirable_heights = [h for h in heights_asc if height_comp_map[h]["bytes"] <= quota_limit]
                        rec_h = acquirable_heights[-1] if acquirable_heights else (min(heights_asc[-1], 1080) if heights_asc else 1080)

                        # Determine top native stream (for best_video_audio)
                        rec_h_fmts = [f for f in video_formats if f.get("height") == rec_h]
                        best_native_rec = next(iter(sorted(
                            rec_h_fmts,
                            key=lambda x: estimate_stream_bytes(x, dur_sec, default_kbps=3000) or 0,
                            reverse=True
                        )), None) or next(iter(sorted(
                            video_formats,
                            key=lambda x: estimate_stream_bytes(x, dur_sec, default_kbps=3000) or 0,
                            reverse=True
                        )), None)

                        v_native_bytes = estimate_stream_bytes(best_native_rec, dur_sec, default_kbps=3500) or 0
                        rec_native_size = v_native_bytes + audio_native_bytes

                        # Detect truthful codecs & HDR
                        v_codec_clean = clean_codec_name(best_native_rec.get("vcodec") if best_native_rec else None)
                        a_codec_clean = clean_codec_name(best_any_audio.get("acodec") if best_any_audio else None)
                        native_codec_label = f"{v_codec_clean}/{a_codec_clean}"
                        is_hdr = bool(best_native_rec and best_native_rec.get("dynamic_range") in ["HDR", "HDR10", "HLG"])
                        hdr_suffix = " HDR" if is_hdr else ""

                        # 1. BEST QUALITY COMPOSITE (VIDEO + AUDIO) - MUST BE FIRST!
                        formats.append(FormatOption(
                            format_id="best_video_audio",
                            file_type="video",
                            mime_type="video/mp4",
                            resolution=f"{rec_h}p",
                            codec=native_codec_label,
                            estimated_size_bytes=rec_native_size,
                            quality_label=f"★ Best Quality ({get_friendly_resolution_name(rec_h)}{hdr_suffix}) • with Audio",
                            has_audio=True,
                            has_video=True,
                            category="recommended"
                        ))

                        # 2. RESOLUTION-SPECIFIC VIDEO + AUDIO PRESETS (Descending order: 1080p -> 720p -> ...)
                        for h in sorted(heights_asc, reverse=True):
                            formats.append(FormatOption(
                                format_id=f"best_{h}p_mp4",
                                file_type="video",
                                mime_type="video/mp4",
                                resolution=f"{h}p",
                                codec="h264/aac",
                                estimated_size_bytes=height_comp_map[h]["bytes"],
                                quality_label=f"{get_friendly_resolution_name(h)} • with Audio",
                                has_audio=True,
                                has_video=True,
                                category="recommended"
                            ))

                    # 3. AUDIO-ONLY PRESETS
                    if has_audio:
                        formats.append(FormatOption(
                            format_id="best_audio_m4a",
                            file_type="audio",
                            mime_type="audio/mp4",
                            resolution=None,
                            codec="aac",
                            estimated_size_bytes=best_audio_bytes,
                            quality_label="Best Quality Audio (M4A / AAC)",
                            has_audio=True,
                            has_video=False,
                            category="audio_only"
                        ))
                        mp3_bytes = estimate_stream_bytes(None, dur_sec, default_kbps=320) or best_audio_bytes
                        formats.append(FormatOption(
                            format_id="best_audio_mp3",
                            file_type="audio",
                            mime_type="audio/mpeg",
                            resolution=None,
                            codec="mp3",
                            estimated_size_bytes=mp3_bytes,
                            quality_label="Standard Audio (MP3 320k)",
                            has_audio=True,
                            has_video=False,
                            category="audio_only"
                        ))

                    if formats:
                        assets.append(MediaAsset(
                            asset_id="primary_media",
                            asset_type="video" if has_video else "audio",
                            title=title,
                            url=resolved_url,
                            thumbnail_url=thumbnail_url,
                            duration_seconds=float(duration) if duration else None,
                            mime_type="video/mp4" if has_video else "audio/mp4"
                        ))
        except Exception:
            pass

        # Fallback inspection for HTML page with embedded media tags
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
                            quality_label=f"Embedded Video {idx+1} (MP4)",
                            download_url=full_v_url,
                            has_audio=True,
                            has_video=True,
                            category="recommended"
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
                            download_url=full_s_url,
                            has_audio=True,
                            has_video=True,
                            category="recommended"
                        ))
            except Exception:
                pass

        # Fallback inspection to Cobalt if direct scrapers failed or encountered anti-bot wall
        if not formats:
            try:
                from providers.cobalt.provider import CobaltProvider
                cobalt = CobaltProvider()
                if cobalt.can_handle(url):
                    cobalt_insp = await cobalt.inspect(url)
                    if cobalt_insp.is_permitted and cobalt_insp.formats:
                        return cobalt_insp
            except Exception:
                pass

        # Fallback inspection to Autonomous Browser Sniffer for JS-rendered dynamic media
        if not formats:
            try:
                from providers.browser_sniffer.provider import BrowserSnifferProvider
                sniffer = BrowserSnifferProvider()
                sniffer_insp = await sniffer.inspect(url)
                if sniffer_insp.is_permitted and sniffer_insp.formats:
                    return sniffer_insp
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

        # Invariant: If video is present, primary mime must be video/mp4, NEVER audio/mp4!
        primary_mime = "video/mp4" if any(f.file_type == "video" for f in formats) else "audio/mp4"

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
            capabilities=["media_extraction", "stream_muxing", "video_audio_mux"],
            mime_type=primary_mime,
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
            # Attempt direct Cobalt fallback
            from providers.cobalt.provider import CobaltProvider
            cobalt = CobaltProvider()
            if cobalt.can_handle(url):
                return await cobalt.acquire(
                    url=url,
                    format_id=format_id,
                    destination_path=destination_path,
                    progress_callback=progress_callback,
                    timeout_seconds=timeout_seconds,
                    max_size_bytes=max_size_bytes
                )
            raise ValueError(f"Cannot acquire media: {'; '.join(inspection.errors) or 'No formats available.'}")

        target_format = next((f for f in inspection.formats if f.format_id == format_id), inspection.formats[0])

        # If it's a composite or yt-dlp format (like best_video_audio, best_1080p_mp4, best_audio_m4a)
        if format_id.startswith("best_") or not target_format.download_url:
            import yt_dlp
            ext = "mp4" if target_format.file_type == "video" else "m4a"

            # Determine yt-dlp format selector
            postprocessors = None
            if target_format.file_type == "audio":
                fmt_spec = "bestaudio/best"
                ext = "m4a" if "m4a" in format_id else ("mp3" if "mp3" in format_id else "m4a")
                postprocessors = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": ext,
                    "preferredquality": "320" if ext == "mp3" else "192"
                }]
            elif format_id == "best_video_audio":
                # High-fidelity / native stream (can be VP9/AV1/Opus/HDR)
                fmt_spec = "bestvideo+bestaudio/best[vcodec!=none]"
                ext = "mp4"
            else:
                m_h = re.search(r'best_(\d+)p', format_id)
                if m_h:
                    h = m_h.group(1)
                    # Prefer compatible H.264 (avc1) video and AAC (mp4a) audio for standard resolution presets
                    fmt_spec = (
                        f"bestvideo[height<={h}][vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
                        f"bestvideo[height<={h}][vcodec^=avc1]+bestaudio/"
                        f"bestvideo[height<={h}]+bestaudio[acodec^=mp4a]/"
                        f"bestvideo[height<={h}]+bestaudio/"
                        f"best[height<={h}][vcodec!=none]"
                    )
                else:
                    fmt_spec = "bestvideo+bestaudio/best[vcodec!=none]"
                ext = "mp4"

            temp_stem = f"ytdl_{uuid.uuid4().hex[:8]}"
            temp_template = str(destination_path.parent / f"{temp_stem}.%(ext)s")

            ydl_opts = {
                "format": fmt_spec,
                "outtmpl": temp_template,
                "merge_output_format": "mp4" if ext == "mp4" else None,
                "quiet": True,
                "no_warnings": True,
                "overwrites": True,
            }
            if postprocessors:
                ydl_opts["postprocessors"] = postprocessors

            loop = asyncio.get_running_loop()
            target_target_url = inspection.resolved_url or url

            def _ytdl_run():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([target_target_url])

            try:
                await loop.run_in_executor(None, _ytdl_run)

                # Discover generated file
                candidates = list(destination_path.parent.glob(f"{temp_stem}.*"))
                if not candidates:
                    raise RuntimeError(f"Media extraction failed to produce file for format '{format_id}'.")
                actual_temp_file = candidates[0]

                # Move to destination_path
                if destination_path.exists():
                    destination_path.unlink()
                actual_temp_file.rename(destination_path)

                # Integrity & Fidelity Supervisor check:
                actual_vcodec = ""
                actual_acodec = ""
                if target_format.file_type == "video":
                    import shutil, subprocess
                    ffprobe_bin = shutil.which("ffprobe")
                    ffmpeg_bin = shutil.which("ffmpeg")
                    if ffprobe_bin:
                        probe_v = subprocess.run(
                            [ffprobe_bin, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", str(destination_path)],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        actual_vcodec = probe_v.stdout.strip().lower() if probe_v.returncode == 0 else ""
                        if not actual_vcodec:
                            destination_path.unlink(missing_ok=True)
                            raise RuntimeError(f"Media extraction produced audio-only stream for requested video format '{format_id}'.")

                        probe_a = subprocess.run(
                            [ffprobe_bin, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", str(destination_path)],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        actual_acodec = probe_a.stdout.strip().lower() if probe_a.returncode == 0 else ""

                        # Check if format contracted compatible H.264 + AAC
                        expected_codec = (target_format.codec or "").lower()
                        needs_transcode = False
                        if "h264" in expected_codec and actual_vcodec not in ["h264", "avc1"]:
                            needs_transcode = True
                        if "aac" in expected_codec and actual_acodec not in ["aac", "mp4a"]:
                            needs_transcode = True

                        if needs_transcode and ffmpeg_bin:
                            transcode_temp = destination_path.parent / f"transcoded_{uuid.uuid4().hex[:8]}.mp4"
                            cmd = [
                                ffmpeg_bin, "-y", "-i", str(destination_path),
                                "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                                "-c:a", "aac", "-b:a", "128k",
                                "-movflags", "+faststart",
                                str(transcode_temp)
                            ]
                            res = subprocess.run(cmd, capture_output=True, timeout=180)
                            if res.returncode == 0 and transcode_temp.exists() and transcode_temp.stat().st_size > 0:
                                destination_path.unlink(missing_ok=True)
                                transcode_temp.rename(destination_path)
                                actual_vcodec = "h264"
                                actual_acodec = "aac"
            except Exception as ytdl_err:
                # Anti-bot resilience: Fallback to Cobalt adapter if applicable
                from providers.cobalt.provider import CobaltProvider
                cobalt = CobaltProvider()
                if cobalt.can_handle(target_target_url):
                    try:
                        return await cobalt.acquire(
                            url=target_target_url,
                            format_id=format_id,
                            destination_path=destination_path,
                            progress_callback=progress_callback,
                            timeout_seconds=timeout_seconds,
                            max_size_bytes=max_size_bytes
                        )
                    except Exception as cobalt_err:
                        raise RuntimeError(f"Both primary yt-dlp ({ytdl_err}) and Cobalt fallback ({cobalt_err}) failed.")
                raise ytdl_err

            file_size = destination_path.stat().st_size
            if file_size > max_size_bytes:
                destination_path.unlink(missing_ok=True)
                raise ValueError(f"Acquired media size ({file_size} bytes) exceeds limit ({max_size_bytes} bytes)")

            sha256 = hashlib.sha256()
            with open(destination_path, "rb") as f:
                while chunk := f.read(65536):
                    sha256.update(chunk)

            if progress_callback:
                await progress_callback(file_size, file_size)

            res_dict = {
                "filename": f"media_{uuid.uuid4().hex[:8]}.{ext}",
                "mime_type": "video/mp4" if ext == "mp4" else "audio/mp4",
                "transferred_bytes": file_size,
                "total_bytes": file_size,
                "sha256": sha256.hexdigest(),
            }
            if actual_vcodec:
                res_dict["vcodec"] = actual_vcodec
            if actual_acodec:
                res_dict["acodec"] = actual_acodec
            if actual_vcodec or actual_acodec:
                res_dict["codec"] = f"{actual_vcodec}/{actual_acodec}" if actual_vcodec and actual_acodec else actual_vcodec or actual_acodec
            return res_dict

        # Otherwise fallback to direct HTTP streaming
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
