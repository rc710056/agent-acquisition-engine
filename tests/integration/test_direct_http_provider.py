import pytest
import uvicorn
import asyncio
import tempfile
from pathlib import Path
from fastapi import FastAPI, Response
from providers.direct_http.provider import DirectHTTPProvider

# Create mock test server app
test_app = FastAPI()

TEST_PAYLOAD = b"%PDF-1.4 Mock PDF binary content for testing acquisition engine integrity"

@test_app.head("/test.pdf")
async def mock_head():
    return Response(
        content=b"",
        headers={
            "Content-Type": "application/pdf",
            "Content-Length": str(len(TEST_PAYLOAD)),
            "Content-Disposition": 'attachment; filename="official_report.pdf"',
            "Accept-Ranges": "bytes"
        }
    )

@test_app.get("/test.pdf")
async def mock_get():
    return Response(
        content=TEST_PAYLOAD,
        headers={
            "Content-Type": "application/pdf",
            "Content-Length": str(len(TEST_PAYLOAD)),
            "Content-Disposition": 'attachment; filename="official_report.pdf"'
        }
    )

@pytest.fixture(scope="module")
def mock_server_port():
    return 8999

@pytest.fixture(scope="module", autouse=True)
def run_mock_server(mock_server_port):
    config = uvicorn.Config(test_app, host="127.0.0.1", port=mock_server_port, log_level="warning")
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
async def test_direct_http_provider_lifecycle(mock_server_port, monkeypatch):
    provider = DirectHTTPProvider()
    target_url = f"http://127.0.0.1:{mock_server_port}/test.pdf"

    # In tests, bypass SSRF for local mock server URL
    from apps.api.app.security.ssrf import SSRFValidator
    monkeypatch.setattr(SSRFValidator, "validate_url", lambda url: (True, None))

    # 1. Inspect
    inspection = await provider.inspect(target_url)
    assert inspection.is_permitted is True
    assert inspection.mime_type == "application/pdf"
    assert inspection.estimated_size_bytes == len(TEST_PAYLOAD)

    # 2. List formats
    formats = await provider.list_formats(target_url)
    assert len(formats) >= 1
    assert formats[0].format_id == "original"
    assert formats[0].file_type == "document"

    # 3. Acquire
    with tempfile.TemporaryDirectory() as tmp_dir:
        dest_path = Path(tmp_dir) / "downloaded.pdf"
        progress_events = []

        async def on_progress(transferred, total):
            progress_events.append((transferred, total))

        result = await provider.acquire(
            target_url,
            format_id="original",
            destination_path=dest_path,
            progress_callback=on_progress
        )

        assert dest_path.exists()
        assert result["filename"] == "official_report.pdf"
        assert result["transferred_bytes"] == len(TEST_PAYLOAD)
        assert len(progress_events) > 0

        # 4. Verify
        verification = provider.verify(dest_path)
        assert verification.is_valid is True
        assert verification.size_bytes == len(TEST_PAYLOAD)
        assert len(verification.sha256) == 64
