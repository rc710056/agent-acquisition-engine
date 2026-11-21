import pytest
import subprocess
import json
import asyncio
from pathlib import Path

from apps.api.app.models.database import init_db
from providers.registry import provider_registry
from providers.permitted_media.provider import PermittedMediaProvider
from apps.api.app.services.verification import FileVerifier

@pytest.mark.asyncio
async def test_youtube_format_presentation_and_audio_inclusion():
    """
    Verifies that inspecting a platform media URL (like YouTube) results in:
    1. primary_mime is video/mp4 (NOT audio/mp4).
    2. Default format (formats[0]) is best_video_audio with has_audio=True.
    3. Distinct resolution presets are offered with clear human-readable quality labels.
    4. Audio-only options are categorized under audio_only.
    """
    await init_db()
    provider = provider_registry.get_provider("permitted_media")
    assert provider is not None

    url = "https://youtu.be/kX7MlVtU9AA"
    inspection = await provider.inspect(url)

    assert inspection.is_permitted is True
    # Invariant: video page must NOT identify as audio/mp4
    assert inspection.mime_type == "video/mp4"
    assert len(inspection.formats) > 0

    # Default format must be best video + audio
    default_fmt = inspection.formats[0]
    assert default_fmt.format_id == "best_video_audio"
    assert default_fmt.file_type == "video"
    assert default_fmt.has_audio is True
    assert default_fmt.has_video is True
    assert "with Audio" in default_fmt.quality_label

    # Check resolution presets exist
    fmt_ids = [f.format_id for f in inspection.formats]
    assert any("p_mp4" in fid for fid in fmt_ids)
    assert any("audio" in fid or "best_" in fid for fid in fmt_ids)

    # Check audio-only preset
    audio_fmts = [f for f in inspection.formats if f.category == "audio_only"]
    assert len(audio_fmts) > 0
    assert audio_fmts[0].file_type == "audio"
    assert audio_fmts[0].has_audio is True
    assert audio_fmts[0].has_video is False

@pytest.mark.asyncio
async def test_media_stream_muxing_with_ffmpeg(tmp_path):
    """
    Acquires a video using the composite preset 'best_360p_mp4' and verifies
    using ffprobe that BOTH video stream AND audio stream are multiplexed
    into the final MP4 container.
    """
    provider = provider_registry.get_provider("permitted_media")
    assert provider is not None

    # Using CC0 public domain short video from YouTube or MDN
    # Big Buck Bunny short or public YouTube clip
    target_url = "https://youtu.be/aqz-KE-bpKQ" # Big Buck Bunny 60fps 4K official short clip
    dest_file = tmp_path / "muxed_test_video.mp4"

    # Acquire with best video + audio
    acquire_res = await provider.acquire(target_url, "best_360p_mp4", dest_file, timeout_seconds=120)
    assert dest_file.exists()
    assert dest_file.stat().st_size > 0

    # Inspect file streams using ffprobe
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=codec_type,codec_name,width,height",
        "-of", "json",
        str(dest_file)
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    probe_data = json.loads(proc.stdout)
    streams = probe_data.get("streams", [])
    codec_types = [s.get("codec_type") for s in streams]

    print("Muxed streams detected by ffprobe:", codec_types)
    assert "video" in codec_types, "Output file must contain a video stream"
    assert "audio" in codec_types, "Output file must contain an audio stream (multiplexed with ffmpeg)"

    # File verification
    v_res = FileVerifier.verify_file(dest_file, expected_mime="video/mp4", expected_sha256=acquire_res["sha256"])
    assert v_res.is_valid is True
