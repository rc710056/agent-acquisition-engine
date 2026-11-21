import pytest
from packages.shared_schemas.models import FormatOption
from providers.permitted_media.provider import estimate_stream_bytes, PermittedMediaProvider
from services.mcp_server.server import describe_capabilities, make_error_envelope, make_success_envelope, mcp

@pytest.mark.asyncio
async def test_format_size_estimation_from_bitrate_and_duration():
    # 1. Exact filesize
    raw_fmt_exact = {"filesize": 10_000_000}
    assert estimate_stream_bytes(raw_fmt_exact, duration_seconds=60) == 10_000_000

    # 2. Approx filesize
    raw_fmt_approx = {"filesize_approx": 8_500_000}
    assert estimate_stream_bytes(raw_fmt_approx, duration_seconds=60) == 8_500_000

    # 3. Bitrate (tbr in kbps) * duration (seconds)
    # 1000 kbps * 1000 / 8 * 10 seconds = 1,250,000 bytes
    raw_fmt_tbr = {"tbr": 1000}
    assert estimate_stream_bytes(raw_fmt_tbr, duration_seconds=10) == 1_250_000

    # 4. Fallback default kbps
    # default 1500 kbps * 1000 / 8 * 10 seconds = 1,875,000 bytes
    assert estimate_stream_bytes(None, duration_seconds=10, default_kbps=1500) == 1_875_000

@pytest.mark.asyncio
async def test_describe_capabilities_manifest():
    res = await describe_capabilities()
    assert res["ok"] is True
    assert res["error"] is None
    assert "data" in res
    assert res["engine_version"] == "0.2.0"
    assert "policy_limits" in res
    assert res["policy_limits"]["unknown_size_requires_approval"] is True
    assert res["policy_limits"]["approval_threshold_bytes"] == 52_428_800
    assert len(res["providers"]) >= 1
    assert "adaptive_video_audio_muxing" in res["capabilities"]

@pytest.mark.asyncio
async def test_describe_capabilities_registered_in_fastmcp():
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "describe_capabilities" in tool_names
    assert "inspect_source" in tool_names
    assert "start_acquisition" in tool_names

def test_structured_error_envelope_backward_compatibility():
    # Test error envelope has string error for legacy assert "error" in res,
    # plus machine-readable codes and remediation
    err = make_error_envelope(
        code="APPROVAL_REQUIRED",
        message="Operator approval is required (file size exceeds 50 MB)",
        remediation="Call request_approval(source_id, format_id, reason)"
    )
    assert err["ok"] is False
    assert isinstance(err["error"], str)
    assert "operator approval is required" in err["error"].lower()
    assert err["error_code"] == "APPROVAL_REQUIRED"
    assert err["error_envelope"]["remediation"] == "Call request_approval(source_id, format_id, reason)"
    assert err["meta"]["engine_version"] == "0.2.0"

def test_structured_success_envelope_backward_compatibility():
    succ = make_success_envelope({"job_id": "job_12345", "state": "queued"})
    assert succ["ok"] is True
    assert succ["error"] is None
    assert succ["job_id"] == "job_12345"
    assert succ["state"] == "queued"
    assert succ["data"]["job_id"] == "job_12345"
    assert succ["meta"]["engine_version"] == "0.2.0"
