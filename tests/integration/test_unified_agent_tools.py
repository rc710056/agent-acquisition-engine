import pytest
import uvicorn
import asyncio
import hashlib
from fastapi import FastAPI, Response
from pathlib import Path

from apps.api.app.models.database import init_db
from services.mcp_server.server import preview_media, acquire_media

# Mock Server for Fast Deterministic Media Testing
mock_media_app = FastAPI()
SAMPLE_VIDEO_PAYLOAD = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + (b"\x00" * 4096)
SAMPLE_AUDIO_PAYLOAD = b"ID3\x03\x00\x00\x00\x00\x00#" + (b"\x00" * 2048)

@mock_media_app.head("/clip.mp4")
async def mock_video_head():
    return Response(
        content=b"",
        headers={
            "Content-Type": "video/mp4",
            "Content-Length": str(len(SAMPLE_VIDEO_PAYLOAD)),
            "Content-Disposition": 'inline; filename="sample_reel.mp4"',
            "Accept-Ranges": "bytes"
        }
    )

@mock_media_app.get("/clip.mp4")
async def mock_video_get():
    return Response(
        content=SAMPLE_VIDEO_PAYLOAD,
        headers={
            "Content-Type": "video/mp4",
            "Content-Length": str(len(SAMPLE_VIDEO_PAYLOAD)),
            "Content-Disposition": 'inline; filename="sample_reel.mp4"'
        }
    )

@pytest.fixture(scope="module")
def mock_tools_port():
    return 8996

@pytest.fixture(scope="module", autouse=True)
def run_mock_server(mock_tools_port):
    config = uvicorn.Config(mock_media_app, host="127.0.0.1", port=mock_tools_port, log_level="warning")
    server = uvicorn.Server(config)

    loop = asyncio.new_event_loop()
    import threading
    thread = threading.Thread(target=lambda: loop.run_until_complete(server.serve()), daemon=True)
    thread.start()

    import time
    time.sleep(0.5)
    yield
    server.should_exit = True

@pytest.mark.asyncio
async def test_preview_media_generates_interactive_card_and_choices(mock_tools_port, monkeypatch):
    """
    Verifies that preview_media inspects the URL, generates an interactive playable
    preview card, and structures human-readable download actions for the user.
    """
    from apps.api.app.security.ssrf import SSRFValidator
    monkeypatch.setattr(SSRFValidator, "validate_url", lambda u: (True, None))
    await init_db()

    target_url = f"http://127.0.0.1:{mock_tools_port}/clip.mp4"
    res = await preview_media(target_url)

    assert res["success"] is True
    data = res["data"]
    assert data["url"] == target_url
    assert "options" in data
    assert len(data["options"]) > 0
    assert "interactive_card" in data
    assert "### 📥 Media Preview" in data["interactive_card"]
    assert "prompt_to_user" in data
    assert "Would you like me to download" in data["prompt_to_user"]

@pytest.mark.asyncio
async def test_acquire_media_single_turn_fulfillment(mock_tools_port, monkeypatch):
    """
    Verifies that acquire_media autonomously executes inspect, auto-approval,
    download, and verification in ONE single tool turn, returning verified download URLs.
    """
    from apps.api.app.security.ssrf import SSRFValidator
    from apps.api.app.services.verification import VerificationResult, FileVerifier
    monkeypatch.setattr(SSRFValidator, "validate_url", lambda u: (True, None))
    monkeypatch.setattr(
        FileVerifier,
        "verify_file",
        staticmethod(lambda file_path, expected_hash=None, expected_size=None, expected_mime=None, **kwargs: VerificationResult(
            is_valid=True,
            size_bytes=len(SAMPLE_VIDEO_PAYLOAD),
            sha256=hashlib.sha256(SAMPLE_VIDEO_PAYLOAD).hexdigest(),
            detected_mime="video/mp4",
            errors=[],
            warnings=[]
        ))
    )
    await init_db()

    target_url = f"http://127.0.0.1:{mock_tools_port}/clip.mp4"
    res = await acquire_media(target_url, format_type="video", auto_approve=True)

    assert res["success"] is True
    data = res["data"]
    assert "artifact_id" in data
    assert "download_url" in data
    assert "preview_url" in data
    assert data["is_verified"] is True
    assert data["size_bytes"] == len(SAMPLE_VIDEO_PAYLOAD)
    assert data["sha256"] == hashlib.sha256(SAMPLE_VIDEO_PAYLOAD).hexdigest()
