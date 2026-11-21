import pytest
from apps.api.app.models.database import init_db, async_session_factory
from apps.api.app.models.entities import Source, SourceOption, UserApproval
from services.mcp_server.server import (
    _get_default_user_id,
    preflight_acquisition,
    start_acquisition
)

@pytest.mark.asyncio
async def test_approval_gate_enforcement():
    await init_db()

    # Create a source and format that exceeds 50MB
    async with async_session_factory() as session:
        src = Source(
            url="https://example.com/huge_dataset.zip",
            provider_id="direct_http",
            content_type="application/zip",
            estimated_size_bytes=104_857_600, # 100 MB
            is_permitted=True
        )
        session.add(src)
        await session.flush()

        opt = SourceOption(
            source_id=src.id,
            format_id="original",
            file_type="archive",
            mime_type="application/zip",
            estimated_size_bytes=104_857_600,
            quality_label="original"
        )
        session.add(opt)
        await session.commit()
        src_id = src.id

    # 1. Preflight must indicate approval required
    pf = await preflight_acquisition(source_id=src_id, format_id="original")
    assert pf["can_acquire"] is True
    assert pf["requires_approval"] is True
    assert "exceeds 50 mb" in pf["approval_reason"].lower()

    # 2. Attempting start_acquisition WITHOUT approval_id must fail
    res_no_approval = await start_acquisition(source_id=src_id, format_id="original")
    assert "error" in res_no_approval
    assert "operator approval is required" in res_no_approval["error"].lower()

    # 3. Create pending approval
    async with async_session_factory() as session:
        user_id = await _get_default_user_id(session)
        appr = UserApproval(
            user_id=user_id,
            source_id=src_id,
            format_id="original",
            status="pending",
            reason="Research dataset needed",
            estimated_size_bytes=104_857_600
        )
        session.add(appr)
        await session.commit()
        appr_id = appr.id

    # Attempting start_acquisition with pending approval must fail
    res_pending = await start_acquisition(source_id=src_id, format_id="original", approval_id=appr_id)
    assert "error" in res_pending
    assert "unapproved" in res_pending["error"].lower()

    # 4. Mark approval as approved
    async with async_session_factory() as session:
        appr_record = await session.get(UserApproval, appr_id)
        appr_record.status = "approved"
        await session.commit()

    # Attempting start_acquisition with approved approval must succeed
    res_approved = await start_acquisition(source_id=src_id, format_id="original", approval_id=appr_id)
    assert "job_id" in res_approved
    assert res_approved["state"] == "queued"

@pytest.mark.asyncio
async def test_unknown_size_requires_operator_approval():
    await init_db()

    # Create a source with unknown size (estimated_size_bytes=None)
    async with async_session_factory() as session:
        src = Source(
            url="https://example.com/stream_unknown_size.m3u8",
            provider_id="direct_http",
            content_type="video/mp4",
            estimated_size_bytes=None,
            is_permitted=True
        )
        session.add(src)
        await session.flush()

        opt = SourceOption(
            source_id=src.id,
            format_id="live_stream",
            file_type="video",
            mime_type="video/mp4",
            estimated_size_bytes=None,
            quality_label="Live Stream"
        )
        session.add(opt)
        await session.commit()
        src_id = src.id

    # 1. Preflight must require approval because size is unknown
    pf = await preflight_acquisition(source_id=src_id, format_id="live_stream")
    assert pf["can_acquire"] is True
    assert pf["requires_approval"] is True
    assert "unknown" in pf["approval_reason"].lower()

    # 2. Start acquisition without approval must fail
    res_no_appr = await start_acquisition(source_id=src_id, format_id="live_stream")
    assert "error" in res_no_appr
    assert "operator approval is required" in res_no_appr["error"].lower()
    assert res_no_appr["error_code"] == "APPROVAL_REQUIRED"
