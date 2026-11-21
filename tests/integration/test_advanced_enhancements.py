import pytest
import asyncio
import uuid
import json
import zipfile
from pathlib import Path
from starlette.responses import Response, JSONResponse
from fastapi import FastAPI
import uvicorn
import threading
import httpx

from apps.api.app.models.database import init_db, async_session_factory
from apps.api.app.models.entities import User, Source, SourceOption, AcquisitionJob, Artifact
from services.mcp_server.server import (
    inspect_source,
    list_formats,
    preflight_acquisition,
    start_acquisition,
    get_job_status,
    get_artifact
)
from services.acquisition_worker.worker import AcquisitionWorker
from providers.registry import provider_registry
from providers.gallery_dl.provider import GalleryDLProvider
from providers.cobalt.provider import CobaltProvider
from packages.shared_schemas.models import SourceType
from apps.api.app.services.storage import storage_service

# Mock Cobalt API server
cobalt_mock_app = FastAPI()

SAMPLE_VIDEO_DATA = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 4096

@cobalt_mock_app.post("/")
@cobalt_mock_app.post("/api/json")
async def mock_cobalt_post(payload: dict):
    # Simulates Cobalt API v10 / v7 response
    return JSONResponse({
        "status": "redirect",
        "url": "http://127.0.0.1:9099/stream/test_media.mp4",
        "filename": "resilient_social_video.mp4"
    })

@cobalt_mock_app.get("/stream/test_media.mp4")
async def mock_cobalt_stream():
    return Response(content=SAMPLE_VIDEO_DATA, media_type="video/mp4")

@pytest.fixture(scope="module", autouse=True)
def run_cobalt_mock_server():
    server = uvicorn.Server(config=uvicorn.Config(cobalt_mock_app, host="127.0.0.1", port=9099, log_level="error"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    import time
    time.sleep(0.5)
    yield
    server.should_exit = True

@pytest.mark.asyncio
async def test_feature_1_deduplication_cache_instant_fulfillment():
    """
    Verifies that once an artifact is acquired, subsequent requests for the
    same canonical URL + format return an instant cache hit (sub-second)
    without dispatching worker downloads or wasting bandwidth.
    """
    await init_db()

    # Step 1: Create a verified artifact in storage
    test_data = b"DEDUPLICATION_TEST_DATA_" + uuid.uuid4().hex.encode()
    temp_path = storage_service.get_temp_path(prefix="cache_test")
    with open(temp_path, "wb") as f:
        f.write(test_data)

    perm_path, clean_name, size, sha256_hash = storage_service.store_artifact(temp_path, "cached_report.pdf")

    unique_url = f"https://example.com/research/paper_{uuid.uuid4().hex[:8]}.pdf"
    cache_key = f"{unique_url}::original"
    import hashlib
    key_hash = hashlib.sha256(cache_key.encode()).hexdigest()

    async with async_session_factory() as session:
        user = User(email=f"cache_user_{uuid.uuid4().hex[:6]}@example.com", hashed_password="pw")
        session.add(user)
        await session.flush()

        source = Source(
            url=unique_url,
            canonical_url=unique_url,
            source_type=SourceType.DIRECT_FILE.value,
            provider_id="direct_http",
            is_permitted=True,
            content_type="application/pdf"
        )
        session.add(source)
        await session.flush()

        opt = SourceOption(
            source_id=source.id,
            format_id="original",
            file_type="document",
            mime_type="application/pdf",
            quality_label="Original Document"
        )
        session.add(opt)

        artifact = Artifact(
            user_id=user.id,
            filename=clean_name,
            mime_type="application/pdf",
            size_bytes=size,
            sha256=sha256_hash,
            storage_path=perm_path.name,
            is_verified=True,
            origin_cache_key=key_hash
        )
        session.add(artifact)
        await session.commit()
        src_id = source.id
        art_id = artifact.id

    # Step 2: Agent calls preflight_acquisition -> Must detect instant cache hit
    preflight = await preflight_acquisition(source_id=src_id, format_id="original")
    assert preflight["can_acquire"] is True
    assert preflight["is_cached"] is True
    assert preflight["cached_artifact_id"] == art_id

    # Step 3: Agent calls start_acquisition -> Must immediately complete with cache hit
    job_res = await start_acquisition(source_id=src_id, format_id="original")
    assert job_res["state"] == "completed"
    assert job_res["is_cached"] is True
    assert job_res["artifact_id"] == art_id
    assert "cache hit" in job_res["message"].lower()

    # Step 4: Status lookup immediately returns completed artifact
    status_res = await get_job_status(job_id=job_res["job_id"])
    assert status_res["state"] == "completed"
    assert status_res["artifact_id"] == art_id

@pytest.mark.asyncio
async def test_feature_2_gallery_dl_provider_inspection_and_routing():
    """
    Verifies that GalleryDLProvider handles image collections and album URLs,
    classifying them as MEDIA_COLLECTION and offering a complete .zip archive format.
    """
    gdl = GalleryDLProvider()
    assert gdl.can_handle("https://imgur.com/gallery/example123") is True
    assert gdl.can_handle("https://www.reddit.com/r/pics/comments/abc123/my_photos/") is True
    assert gdl.can_handle("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is False

    # Inspection test
    inspection = await gdl.inspect("https://imgur.com/gallery/example123")
    assert inspection.source_type == SourceType.MEDIA_COLLECTION
    assert inspection.provider_id == "gallery_dl"
    assert inspection.is_permitted is True

    format_ids = [f.format_id for f in inspection.formats]
    assert "all_images_zip" in format_ids
    assert "first_image" in format_ids

    zip_fmt = next(f for f in inspection.formats if f.format_id == "all_images_zip")
    assert zip_fmt.file_type == "archive"
    assert zip_fmt.mime_type == "application/zip"
    assert zip_fmt.category == "recommended"

@pytest.mark.asyncio
async def test_feature_3_cobalt_universal_adapter_resilience():
    """
    Verifies that CobaltProvider acts as a high-speed, anti-bot fallback
    for social media platforms, properly streaming and verifying media.
    """
    cobalt = CobaltProvider(api_url="http://127.0.0.1:9099")

    assert cobalt.can_handle("https://twitter.com/user/status/123456789") is True
    assert cobalt.can_handle("https://www.tiktok.com/@creator/video/123456789") is True
    assert cobalt.can_handle("https://instagram.com/reel/C89abcdef") is True

    # Test inspection
    inspection = await cobalt.inspect("https://twitter.com/user/status/123456789")
    assert inspection.is_permitted is True
    assert inspection.provider_id == "cobalt"
    assert any(f.format_id == "cobalt_best_video" for f in inspection.formats)

    # Test real acquisition against mock Cobalt server
    target_dest = storage_service.get_temp_path(prefix="cobalt_test")
    progress_recorded = []

    async def on_progress(done, total):
        progress_recorded.append((done, total))

    result = await cobalt.acquire(
        url="https://twitter.com/user/status/123456789",
        format_id="cobalt_best_video",
        destination_path=target_dest,
        progress_callback=on_progress
    )

    assert result["provider"] == "cobalt"
    assert result["mime_type"] == "video/mp4"
    assert result["size_bytes"] == len(SAMPLE_VIDEO_DATA)
    assert target_dest.exists()
    assert len(progress_recorded) > 0

    # Verification
    verification = cobalt.verify(target_dest)
    assert verification.is_valid is True
    assert verification.detected_mime == "video/mp4"
    target_dest.unlink(missing_ok=True)

@pytest.mark.asyncio
async def test_feature_4_permitted_media_fallback_to_cobalt(monkeypatch):
    """
    Verifies that when yt-dlp encounters anti-bot challenges or sign-in blocks,
    PermittedMediaProvider automatically falls back to CobaltProvider and succeeds.
    """
    import yt_dlp
    import os
    from providers.permitted_media.provider import PermittedMediaProvider

    monkeypatch.setenv("COBALT_API_URL", "http://127.0.0.1:9099")

    provider = PermittedMediaProvider()
    target_dest = storage_service.get_temp_path(prefix="fallback_test")

    # Mock yt-dlp to simulate an anti-bot failure
    def mock_failing_download(self, urls):
        raise yt_dlp.utils.DownloadError("Sign in to confirm you're not a bot (anti-bot challenge)")

    monkeypatch.setattr(yt_dlp.YoutubeDL, "download", mock_failing_download)

    result = await provider.acquire(
        url="https://youtube.com/watch?v=kX7MlVtU9AA",
        format_id="best_video_audio",
        destination_path=target_dest
    )

    assert result["provider"] == "cobalt"
    assert result["mime_type"] == "video/mp4"
    assert target_dest.exists()
    assert target_dest.stat().st_size == len(SAMPLE_VIDEO_DATA)

    target_dest.unlink(missing_ok=True)
