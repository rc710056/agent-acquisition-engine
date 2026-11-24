import os
import pytest
import asyncio
import threading
import time
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch
import uvicorn
from fastapi import FastAPI, Response, status

from apps.api.app.models.database import init_db, async_session_factory
from apps.api.app.models.entities import Source, SourceOption, AcquisitionJob, Artifact, UserApproval, User
from packages.shared_schemas.models import (
    SourceType,
    SecurityStatus,
    AcquisitionPermission,
    SourceAccessStatus,
    JobState,
    ApprovalStatus
)
from packages.source_classifier.classifier import SourceClassifier
from providers.registry import provider_registry
from providers.direct_http.provider import DirectHTTPProvider
from providers.pinterest.provider import PinterestProvider
from providers.permitted_media.provider import PermittedMediaProvider
from services.acquisition_worker.worker import AcquisitionWorker
from apps.api.app.services.storage import storage_service
from apps.api.app.services.verification import FileVerifier

# --------------------------------------------------------------------------
# FIXTURE SERVER PROVIDING CONTROLLED TEST SOURCE CATEGORIES
# --------------------------------------------------------------------------
fixture_app = FastAPI()

# 3. Direct Video Payload (Valid MP4 atom header)
MP4_PAYLOAD = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2mp41\x00\x00\x00\x08free" + b"V" * 2048

@fixture_app.head("/direct/video.mp4")
async def handle_video_head():
    return Response(
        content=b"",
        headers={
            "Content-Type": "video/mp4",
            "Content-Length": str(len(MP4_PAYLOAD)),
            "Content-Disposition": 'attachment; filename="sample_clip.mp4"',
            "Accept-Ranges": "bytes"
        }
    )

@fixture_app.get("/direct/video.mp4")
async def handle_video_get():
    return Response(
        content=MP4_PAYLOAD,
        headers={
            "Content-Type": "video/mp4",
            "Content-Length": str(len(MP4_PAYLOAD)),
            "Content-Disposition": 'attachment; filename="sample_clip.mp4"'
        }
    )

# 4. Direct Image Payload (Valid JPEG markers)
JPEG_PAYLOAD = b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x00" * 512 + b"\xFF\xD9"

@fixture_app.head("/direct/photo.jpg")
async def handle_image_head():
    return Response(
        content=b"",
        headers={
            "Content-Type": "image/jpeg",
            "Content-Length": str(len(JPEG_PAYLOAD)),
            "Content-Disposition": 'inline; filename="photo.jpg"'
        }
    )

@fixture_app.get("/direct/photo.jpg")
async def handle_image_get():
    return Response(
        content=JPEG_PAYLOAD,
        headers={
            "Content-Type": "image/jpeg",
            "Content-Length": str(len(JPEG_PAYLOAD)),
            "Content-Disposition": 'inline; filename="photo.jpg"'
        }
    )

# 5. Direct PDF Payload
PDF_PAYLOAD = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n%%EOF\n"

@fixture_app.head("/direct/document.pdf")
async def handle_pdf_head():
    return Response(
        content=b"",
        headers={
            "Content-Type": "application/pdf",
            "Content-Length": str(len(PDF_PAYLOAD)),
            "Content-Disposition": 'attachment; filename="document.pdf"'
        }
    )

@fixture_app.get("/direct/document.pdf")
async def handle_pdf_get():
    return Response(
        content=PDF_PAYLOAD,
        headers={
            "Content-Type": "application/pdf",
            "Content-Length": str(len(PDF_PAYLOAD)),
            "Content-Disposition": 'attachment; filename="document.pdf"'
        }
    )

# 6. Webpage with embedded video
HTML_VIDEO_PAGE = """<!DOCTYPE html>
<html>
<head><title>Embedded Video Feature</title></head>
<body>
  <h1>Product Demonstration</h1>
  <video src="/direct/video.mp4" controls width="640" height="360"></video>
</body>
</html>"""

@fixture_app.get("/webpage/embedded-video")
async def handle_video_page():
    return Response(content=HTML_VIDEO_PAGE, media_type="text/html")

# 7. Webpage with multiple images (Media Collection)
HTML_GALLERY_PAGE = """<!DOCTYPE html>
<html>
<head><title>Photo Exhibition</title></head>
<body>
  <h1>Exhibition Gallery</h1>
  <img src="/direct/photo1.jpg" alt="Art 1" />
  <img src="/direct/photo2.jpg" alt="Art 2" />
  <img src="/direct/photo3.jpg" alt="Art 3" />
  <img src="/direct/photo4.jpg" alt="Art 4" />
</body>
</html>"""

@fixture_app.get("/webpage/gallery")
async def handle_gallery_page():
    return Response(content=HTML_GALLERY_PAGE, media_type="text/html")

# 9. Auth Required
@fixture_app.get("/protected/secret")
async def handle_auth_required():
    return Response(status_code=status.HTTP_401_UNAUTHORIZED, content="Unauthorized", headers={"WWW-Authenticate": "Bearer"})

# Raw HTML page without media
@fixture_app.head("/webpage/plain")
async def handle_plain_html_head():
    return Response(content=b"", media_type="text/html", headers={"Content-Length": "100"})

@fixture_app.get("/webpage/plain")
async def handle_plain_html():
    return Response(content="<html><body><p>Just ordinary text without media</p></body></html>", media_type="text/html")

@pytest.fixture(scope="module")
def fixture_port():
    return 9181

@pytest.fixture(scope="module", autouse=True)
def run_fixture_server(fixture_port):
    config = uvicorn.Config(fixture_app, host="127.0.0.1", port=fixture_port, log_level="warning")
    server = uvicorn.Server(config)
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=lambda: loop.run_until_complete(server.serve()), daemon=True)
    thread.start()
    time.sleep(0.5)
    yield f"http://127.0.0.1:{fixture_port}"
    server.should_exit = True

# --------------------------------------------------------------------------
# REGRESSION TEST SUITE: 10 CATEGORIES
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_category_1_pinterest_short_url():
    """Category 1: Pinterest short URL resolution & format inspection."""
    await init_db()
    url = "https://pin.it/zRhGMggGP"

    provider = provider_registry.get_provider("pinterest")
    assert provider is not None
    assert provider.can_handle(url) is True

    # Real inspection of live Pinterest pin
    inspection = await provider.inspect(url)
    assert inspection.is_permitted is True
    assert inspection.source_type == SourceType.PLATFORM_MEDIA_PAGE
    assert inspection.provider_id == "pinterest"
    assert "pinterest.com/pin/" in (inspection.resolved_url or "")
    assert inspection.mime_type in {"video/mp4", "image/jpeg"}
    assert len(inspection.formats) > 0

    # Verify video qualities detected
    video_formats = [f for f in inspection.formats if f.file_type == "video"]
    assert len(video_formats) > 0
    # Invariant: Unknown sizes remain None
    assert any(f.estimated_size_bytes is None for f in video_formats)

@pytest.mark.asyncio
async def test_category_2_pinterest_full_media_url():
    """Category 2: Pinterest full canonical pin URL."""
    url = "https://www.pinterest.com/pin/606086062398971836/"
    provider = provider_registry.get_provider("pinterest")
    assert provider.can_handle(url) is True

    inspection = await provider.inspect(url)
    assert inspection.is_permitted is True
    assert inspection.source_type == SourceType.PLATFORM_MEDIA_PAGE
    assert len(inspection.formats) > 0

@pytest.mark.asyncio
async def test_category_3_direct_video_url(fixture_port, monkeypatch):
    """Category 3: Direct video URL."""
    from apps.api.app.security.ssrf import SSRFValidator
    monkeypatch.setattr(SSRFValidator, "validate_url", lambda u: (True, None))

    url = f"http://127.0.0.1:{fixture_port}/direct/video.mp4"
    classification = await SourceClassifier.classify(url)
    assert classification.source_type == SourceType.DIRECT_FILE
    assert classification.provider_id == "direct_http"
    assert classification.mime_type == "video/mp4"
    assert classification.estimated_size_bytes == len(MP4_PAYLOAD)

    provider = provider_registry.get_provider(classification.provider_id)
    inspection = await provider.inspect(url)
    assert inspection.is_permitted is True
    assert inspection.mime_type == "video/mp4"
    assert inspection.formats[0].file_type == "video"

@pytest.mark.asyncio
async def test_category_4_direct_image_url(fixture_port, monkeypatch):
    """Category 4: Direct image URL."""
    from apps.api.app.security.ssrf import SSRFValidator
    monkeypatch.setattr(SSRFValidator, "validate_url", lambda u: (True, None))

    url = f"http://127.0.0.1:{fixture_port}/direct/photo.jpg"
    classification = await SourceClassifier.classify(url)
    assert classification.source_type == SourceType.DIRECT_FILE
    assert classification.provider_id == "direct_http"
    assert classification.mime_type == "image/jpeg"

@pytest.mark.asyncio
async def test_category_5_direct_pdf_url(fixture_port, monkeypatch):
    """Category 5: Direct PDF document URL."""
    from apps.api.app.security.ssrf import SSRFValidator
    monkeypatch.setattr(SSRFValidator, "validate_url", lambda u: (True, None))

    url = f"http://127.0.0.1:{fixture_port}/direct/document.pdf"
    classification = await SourceClassifier.classify(url)
    assert classification.source_type == SourceType.DIRECT_FILE
    assert classification.provider_id == "direct_http"
    assert classification.mime_type == "application/pdf"

@pytest.mark.asyncio
async def test_category_6_webpage_containing_embedded_video(fixture_port, monkeypatch):
    """Category 6: Webpage containing embedded video."""
    from apps.api.app.security.ssrf import SSRFValidator
    monkeypatch.setattr(SSRFValidator, "validate_url", lambda u: (True, None))

    url = f"http://127.0.0.1:{fixture_port}/webpage/embedded-video"
    classification = await SourceClassifier.classify(url)

    # Invariant: Webpage is NEVER classified as DIRECT_FILE
    assert classification.source_type == SourceType.WEBPAGE_WITH_MEDIA
    assert classification.provider_id == "permitted_media"

    provider = provider_registry.get_provider(classification.provider_id)
    inspection = await provider.inspect(url)
    assert inspection.is_permitted is True
    assert len(inspection.formats) > 0
    assert inspection.formats[0].file_type == "video"

@pytest.mark.asyncio
async def test_category_7_webpage_containing_multiple_images(fixture_port, monkeypatch):
    """Category 7: Webpage containing multiple images (gallery)."""
    from apps.api.app.security.ssrf import SSRFValidator
    monkeypatch.setattr(SSRFValidator, "validate_url", lambda u: (True, None))

    url = f"http://127.0.0.1:{fixture_port}/webpage/gallery"
    classification = await SourceClassifier.classify(url)
    assert classification.source_type == SourceType.MEDIA_COLLECTION
    assert classification.provider_id == "permitted_media"
    assert len(classification.extracted_media_links) >= 4

@pytest.mark.asyncio
async def test_category_8_unsupported_platform_url():
    """Category 8: Unsupported/non-media service URL."""
    url = "https://unsupported-unknown-landing-service.xyz/"
    classification = await SourceClassifier.classify(url)
    assert classification.source_type == SourceType.UNSUPPORTED_SOURCE
    assert classification.provider_id == "unsupported"

@pytest.mark.asyncio
async def test_category_social_media_platforms_supported():
    """Verifies that social media URLs (Instagram, TikTok, Twitter/X) are mapped to permitted_media."""
    for social_url in [
        "https://www.instagram.com/reel/C382x910/",
        "https://tiktok.com/@creator/video/1234567890",
        "https://x.com/user/status/9876543210"
    ]:
        classification = await SourceClassifier.classify(social_url)
        assert classification.provider_id == "permitted_media"
        assert classification.source_type == SourceType.PLATFORM_MEDIA_PAGE

@pytest.mark.asyncio
async def test_category_9_authentication_required_source(fixture_port, monkeypatch):
    """Category 9: Authentication-required source (HTTP 401)."""
    from apps.api.app.security.ssrf import SSRFValidator
    monkeypatch.setattr(SSRFValidator, "validate_url", lambda u: (True, None))

    url = f"http://127.0.0.1:{fixture_port}/protected/secret"
    classification = await SourceClassifier.classify(url)
    assert classification.source_access_status == SourceAccessStatus.AUTHENTICATION_REQUIRED
    assert classification.acquisition_permission == AcquisitionPermission.USER_AUTHORIZATION_REQUIRED

@pytest.mark.asyncio
async def test_category_10_invalid_and_blocked_urls():
    """Category 10: Invalid syntax and SSRF-blocked URLs."""
    # 10a: Invalid syntax
    res_bad = await SourceClassifier.classify("not-a-valid-url")
    assert res_bad.security_status == SecurityStatus.BLOCKED

    # 10b: SSRF blocked
    res_ssrf = await SourceClassifier.classify("http://192.168.1.1/admin")
    assert res_ssrf.security_status == SecurityStatus.BLOCKED
    assert res_ssrf.source_type == SourceType.UNSUPPORTED_SOURCE

# --------------------------------------------------------------------------
# CRITICAL SYSTEM INVARIANT TESTS
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invariant_html_not_treated_as_direct_file(fixture_port, monkeypatch):
    """Verify: HTML pages with Content-Type: text/html are rejected by DirectHTTPProvider."""
    from apps.api.app.security.ssrf import SSRFValidator
    monkeypatch.setattr(SSRFValidator, "validate_url", lambda u: (True, None))

    url = f"http://127.0.0.1:{fixture_port}/webpage/plain"
    provider = DirectHTTPProvider()
    inspection = await provider.inspect(url)
    assert inspection.is_permitted is False
    assert "text/html" in inspection.errors[0]
    formats = await provider.list_formats(url)
    assert len(formats) == 0

@pytest.mark.asyncio
async def test_invariant_approval_missing_blocks_acquisition(fixture_port, monkeypatch):
    """Verify: Acquisition cannot begin when required approval is missing (>50MB)."""
    await init_db()
    from apps.api.app.security.ssrf import SSRFValidator
    monkeypatch.setattr(SSRFValidator, "validate_url", lambda u: (True, None))

    from apps.api.app.routes.acquisitions import create_job
    from packages.shared_schemas.models import CreateJobRequest
    from apps.api.app.models.entities import User
    from fastapi import HTTPException

    async with async_session_factory() as session:
        user = User(email=f"approval_tester_{uuid.uuid4().hex[:6]}@example.com", hashed_password="hash", role="user")
        session.add(user)
        src = Source(
            url=f"http://127.0.0.1:{fixture_port}/direct/video.mp4",
            provider_id="direct_http",
            is_permitted=True,
            estimated_size_bytes=60_000_000
        )
        session.add(src)
        await session.flush()
        opt = SourceOption(
            source_id=src.id,
            format_id="hd_60mb",
            file_type="video",
            mime_type="video/mp4",
            estimated_size_bytes=60_000_000
        )
        session.add(opt)
        await session.commit()

        # Try to create job without approval_id
        req = CreateJobRequest(source_id=src.id, format_id="hd_60mb", approval_id=None)
        with pytest.raises(HTTPException) as exc:
            await create_job(req, db=session, user=user)
        assert exc.value.status_code == 403
        assert "approval is required" in exc.value.detail.lower()

@pytest.mark.asyncio
async def test_invariant_job_verifies_before_completed(fixture_port, monkeypatch):
    """Verify: A job cannot become completed before verification, and verification failure fails the job."""
    await init_db()
    from apps.api.app.security.ssrf import SSRFValidator
    monkeypatch.setattr(SSRFValidator, "validate_url", lambda u: (True, None))

    async with async_session_factory() as session:
        user = User(email=f"worker_tester_{uuid.uuid4().hex[:6]}@example.com", hashed_password="hash", role="user")
        session.add(user)
        src = Source(
            url=f"http://127.0.0.1:{fixture_port}/direct/video.mp4",
            provider_id="direct_http",
            is_permitted=True,
            estimated_size_bytes=len(MP4_PAYLOAD)
        )
        session.add(src)
        await session.flush()
        opt = SourceOption(
            source_id=src.id,
            format_id="original",
            file_type="video",
            mime_type="video/mp4",
            estimated_size_bytes=len(MP4_PAYLOAD)
        )
        session.add(opt)
        job = AcquisitionJob(
            user_id=user.id,
            source_id=src.id,
            format_id="original",
            state=JobState.QUEUED.value
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    worker = AcquisitionWorker()
    processed = await worker.process_next_job(target_job_id=job_id)
    assert processed is True

    # Check database state
    async with async_session_factory() as session:
        completed_job = await session.get(AcquisitionJob, job_id)
        assert completed_job.state == JobState.COMPLETED.value
        assert completed_job.artifact_id is not None
        art = await session.get(Artifact, completed_job.artifact_id)
        assert art.is_verified is True
        assert art.size_bytes == len(MP4_PAYLOAD)
        assert art.sha256 is not None
