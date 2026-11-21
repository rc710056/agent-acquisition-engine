import pytest
import asyncio
import uuid
import httpx
from pathlib import Path

from apps.api.app.main import app
from apps.api.app.models.database import init_db, async_session_factory
from apps.api.app.models.entities import User, Source, SourceOption, AcquisitionJob, Artifact, UserApproval
from services.mcp_server.server import (
    _get_default_user_id,
    inspect_source,
    list_formats,
    preflight_acquisition,
    request_approval,
    start_acquisition,
    get_job_status,
    get_artifact
)
from services.acquisition_worker.worker import AcquisitionWorker
from apps.api.app.services.verification import FileVerifier


async def _approve_as_user(approval_id: str) -> None:
    async with async_session_factory() as session:
        user_id = await _get_default_user_id(session)
        user = await session.get(User, user_id)
        portal_token = user.portal_token

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/approvals/{approval_id}/decision",
            json={"decision": "approved"},
            headers={"Authorization": f"Bearer {portal_token}"}
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_agent_journey_youtube_with_audio():
    """
    Simulates an AI Agent fulfilling:
    'Download this YouTube video in the best quality with audio.'
    """
    await init_db()
    url = "https://youtu.be/aqz-KE-bpKQ" # Big Buck Bunny public clip

    # 1. Agent calls inspect_source
    inspect_res = await inspect_source(url=url)
    assert inspect_res["is_permitted"] is True
    assert inspect_res["source_type"] == "PLATFORM_MEDIA_PAGE"
    assert inspect_res["provider"] == "permitted_media"
    assert inspect_res["mime_type"] == "video/mp4" # Confirms it is NOT audio/mp4
    source_id = inspect_res["source_id"]

    # 2. Agent calls list_formats
    formats_res = await list_formats(source_id=source_id)
    formats = formats_res["formats"]
    assert len(formats) > 0

    # Agent looks for best video with audio
    best_video_audio = next((f for f in formats if f.get("has_audio") and f.get("file_type") == "video"), None)
    assert best_video_audio is not None
    assert best_video_audio["format_id"] == "best_video_audio"

    # 3. Agent checks preflight
    preflight = await preflight_acquisition(source_id=source_id, format_id=best_video_audio["format_id"])
    assert preflight["can_acquire"] is True
    approval_id = None
    if preflight["requires_approval"]:
        approval_res = await request_approval(
            source_id=source_id,
            format_id=best_video_audio["format_id"],
            reason="User approved this media acquisition."
        )
        approval_id = approval_res["approval_id"]
        await _approve_as_user(approval_id)

    # 4. Agent starts acquisition
    job_res = await start_acquisition(
        source_id=source_id,
        format_id=best_video_audio["format_id"],
        approval_id=approval_id
    )
    job_id = job_res["job_id"]
    assert job_res["state"] in {"queued", "completed"}

    # 5. Worker processes job in background if queued
    if job_res["state"] == "queued":
        worker = AcquisitionWorker()
        processed = await worker.process_next_job(target_job_id=job_id)
        assert processed is True

    # 6. Agent polls status until completed
    status_res = await get_job_status(job_id=job_id)
    assert status_res["state"] == "completed"
    assert status_res["artifact_id"] is not None

    # 7. Agent retrieves verified artifact and secure delivery link
    artifact_res = await get_artifact(artifact_id=status_res["artifact_id"])
    assert artifact_res["is_verified"] is True
    assert artifact_res["size_bytes"] > 0
    assert artifact_res["sha256"] is not None
    assert "?token=" in artifact_res["download_url"]

@pytest.mark.asyncio
async def test_agent_journey_audio_only_request():
    """
    Simulates an AI Agent fulfilling:
    'Extract only the audio track from this video.'
    """
    await init_db()
    url = "https://youtu.be/aqz-KE-bpKQ"

    inspect_res = await inspect_source(url=url)
    source_id = inspect_res["source_id"]

    formats_res = await list_formats(source_id=source_id)
    formats = formats_res["formats"]

    # Agent intelligently filters for audio_only preset
    audio_fmt = next((f for f in formats if f.get("category") == "audio_only" or f.get("file_type") == "audio"), None)
    assert audio_fmt is not None
    assert audio_fmt["file_type"] == "audio"

    preflight = await preflight_acquisition(source_id=source_id, format_id=audio_fmt["format_id"])
    assert preflight["can_acquire"] is True
    approval_id = None
    if preflight["requires_approval"]:
        approval_res = await request_approval(
            source_id=source_id,
            format_id=audio_fmt["format_id"],
            reason="User approved this audio acquisition."
        )
        approval_id = approval_res["approval_id"]
        await _approve_as_user(approval_id)

    job_res = await start_acquisition(
        source_id=source_id,
        format_id=audio_fmt["format_id"],
        approval_id=approval_id
    )
    job_id = job_res["job_id"]
    assert job_res["state"] in {"queued", "completed"}

    if job_res["state"] == "queued":
        worker = AcquisitionWorker()
        await worker.process_next_job(target_job_id=job_id)

    status_res = await get_job_status(job_id=job_id)
    assert status_res["state"] == "completed"
    artifact_res = await get_artifact(artifact_id=status_res["artifact_id"])
    assert artifact_res["is_verified"] is True
    assert artifact_res["mime_type"] in {"audio/mp4", "audio/mpeg", "audio/m4a", "audio/x-m4a"}

@pytest.mark.asyncio
async def test_agent_error_handling_ssrf_blocked():
    """
    Simulates an AI Agent receiving a request for an internal loopback IP.
    Verifies agent receives structured error allowing clear user feedback.
    """
    await init_db()
    res = await inspect_source(url="http://127.0.0.1:8000/admin/secrets")
    assert res["is_permitted"] is False
    assert res["security_status"] == "blocked"
    assert any("prohibited" in e.lower() or "ssrf" in e.lower() or "security" in e.lower() or "private" in e.lower() for e in res["errors"])

@pytest.mark.asyncio
async def test_agent_approval_gate_journey():
    """
    Simulates an AI Agent handling a large file (> 50 MB) requiring operator approval.
    """
    await init_db()
    async with async_session_factory() as session:
        src = Source(url="https://example.com/large_dataset.iso", provider_id="direct_http", is_permitted=True)
        session.add(src)
        await session.flush()
        opt = SourceOption(
            source_id=src.id,
            format_id="original",
            file_type="archive",
            mime_type="application/octet-stream",
            estimated_size_bytes=100_000_000
        )
        session.add(opt)
        await session.commit()
        src_id = src.id

    # 1. Agent runs preflight
    preflight = await preflight_acquisition(source_id=src_id, format_id="original")
    assert preflight["requires_approval"] is True
    assert "exceeds 50 mb" in preflight["approval_reason"].lower()

    # 2. Agent tries starting without approval -> blocked
    start_attempt = await start_acquisition(source_id=src_id, format_id="original")
    assert "error" in start_attempt
    assert "approval is required" in start_attempt["error"].lower()

    # 3. Agent requests approval on user's behalf
    approval_res = await request_approval(source_id=src_id, format_id="original", reason="User approved 100MB download")
    appr_id = approval_res["approval_id"]

    # 4. Operator approves in control center
    async with async_session_factory() as session:
        appr = await session.get(UserApproval, appr_id)
        appr.status = "approved"
        await session.commit()

    # 5. Agent restarts acquisition with approval_id -> success
    job_res = await start_acquisition(source_id=src_id, format_id="original", approval_id=appr_id)
    assert "job_id" in job_res
    assert job_res["state"] == "queued"
