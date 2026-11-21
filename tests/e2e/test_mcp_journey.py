import pytest
import uvicorn
import asyncio
import hashlib
from fastapi import FastAPI, Response
from httpx import AsyncClient, ASGITransport

from apps.api.app.main import app as fastapi_app
from apps.api.app.models.database import init_db
from services.mcp_server.server import (
    inspect_source,
    list_formats,
    preflight_acquisition,
    request_approval,
    start_acquisition,
    get_job_status,
    get_artifact
)
from services.acquisition_worker.worker import AcquisitionWorker

# Authorized Mock Test Content Server
e2e_server_app = FastAPI()
E2E_PDF_PAYLOAD = b"%PDF-1.7 Authentic scientific paper downloaded by autonomous AI agent."

@e2e_server_app.head("/research_paper.pdf")
async def mock_paper_head():
    return Response(
        content=b"",
        headers={
            "Content-Type": "application/pdf",
            "Content-Length": str(len(E2E_PDF_PAYLOAD)),
            "Content-Disposition": 'attachment; filename="quantum_algorithms_2026.pdf"',
            "Accept-Ranges": "bytes"
        }
    )

@e2e_server_app.get("/research_paper.pdf")
async def mock_paper_get():
    return Response(
        content=E2E_PDF_PAYLOAD,
        headers={
            "Content-Type": "application/pdf",
            "Content-Length": str(len(E2E_PDF_PAYLOAD)),
            "Content-Disposition": 'attachment; filename="quantum_algorithms_2026.pdf"'
        }
    )

@pytest.fixture(scope="module")
def e2e_port():
    return 8997

@pytest.fixture(scope="module", autouse=True)
def run_e2e_server(e2e_port):
    config = uvicorn.Config(e2e_server_app, host="127.0.0.1", port=e2e_port, log_level="warning")
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
async def test_full_mcp_acquisition_journey(e2e_port, monkeypatch):
    """
    Acceptance Test:
    A compatible AI agent connects to the MCP server and conducts an end-to-end
    acquisition journey:
    inspect -> list formats -> preflight -> start acquisition -> worker execute
    -> poll status -> retrieve artifact -> download from signed expiring link.
    """
    await init_db()

    # Allow mock test server target in SSRF validator for local test
    from apps.api.app.security.ssrf import SSRFValidator
    monkeypatch.setattr(SSRFValidator, "validate_url", lambda url: (True, None))

    test_url = f"http://127.0.0.1:{e2e_port}/research_paper.pdf"

    # Step 1: Agent calls inspect_source
    inspect_result = await inspect_source(url=test_url)
    assert inspect_result["is_permitted"] is True
    assert inspect_result["mime_type"] == "application/pdf"
    assert inspect_result["estimated_size_bytes"] == len(E2E_PDF_PAYLOAD)
    source_id = inspect_result["source_id"]
    assert source_id is not None

    # Step 2: Agent calls list_formats
    formats_result = await list_formats(source_id=source_id)
    assert len(formats_result["formats"]) >= 1
    selected_format = formats_result["formats"][0]["format_id"]
    assert selected_format == "original"

    # Step 3: Agent calls preflight_acquisition
    preflight_result = await preflight_acquisition(source_id=source_id, format_id=selected_format)
    assert preflight_result["can_acquire"] is True
    assert preflight_result["requires_approval"] is False

    # Step 4: Agent calls start_acquisition
    job_start_result = await start_acquisition(source_id=source_id, format_id=selected_format)
    assert "job_id" in job_start_result
    job_id = job_start_result["job_id"]
    assert job_start_result["state"] == "queued"

    # Step 5: Worker executes acquisition in background
    worker = AcquisitionWorker()
    processed = await worker.process_next_job()
    assert processed is True

    # Step 6: Agent checks job status
    status_result = await get_job_status(job_id=job_id)
    assert status_result["state"] == "completed"
    assert status_result["progress_percent"] == 100.0
    assert status_result["artifact_id"] is not None
    artifact_id = status_result["artifact_id"]

    # Step 7: Agent gets verified artifact details
    artifact_result = await get_artifact(artifact_id=artifact_id)
    assert artifact_result["filename"] == "quantum_algorithms_2026.pdf"
    assert artifact_result["size_bytes"] == len(E2E_PDF_PAYLOAD)
    assert artifact_result["is_verified"] is True
    expected_sha256 = hashlib.sha256(E2E_PDF_PAYLOAD).hexdigest()
    assert artifact_result["sha256"] == expected_sha256
    assert "token=" in artifact_result["download_url"]

    # Step 8: Agent downloads payload via signed expiring delivery link
    delivery_url = artifact_result["download_url"]
    path_and_query = delivery_url.split("/api/v1")[-1]

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as client:
        delivery_resp = await client.get(f"/api/v1{path_and_query}")
        assert delivery_resp.status_code == 200
        assert delivery_resp.content == E2E_PDF_PAYLOAD
        assert delivery_resp.headers["content-type"] == "application/pdf"
        assert "quantum_algorithms_2026.pdf" in delivery_resp.headers["content-disposition"]
