import pytest
import uvicorn
import asyncio
from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse
from apps.api.app.models.database import init_db, async_session_factory
from apps.api.app.models.entities import Source, AcquisitionJob, User
from packages.shared_schemas.models import JobState
from services.acquisition_worker.worker import AcquisitionWorker, AcquisitionCancelledError

cancel_test_app = FastAPI()

# Stream 5 chunks of 20KB with pauses
@cancel_test_app.get("/slow_stream.bin")
async def slow_stream():
    async def chunk_generator():
        for i in range(5):
            await asyncio.sleep(0.1)
            yield b"X" * 20480
    return StreamingResponse(chunk_generator(), media_type="application/octet-stream")

@cancel_test_app.head("/slow_stream.bin")
async def slow_head():
    return Response(
        content=b"",
        headers={
            "Content-Type": "application/octet-stream",
            "Content-Length": "102400"
        }
    )

@pytest.fixture(scope="module")
def cancel_server_port():
    return 8996

@pytest.fixture(scope="module", autouse=True)
def run_cancel_server(cancel_server_port):
    config = uvicorn.Config(cancel_test_app, host="127.0.0.1", port=cancel_server_port, log_level="warning")
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
async def test_worker_streaming_cancellation(cancel_server_port, monkeypatch):
    await init_db()

    from apps.api.app.security.ssrf import SSRFValidator
    monkeypatch.setattr(SSRFValidator, "validate_url", lambda url: (True, None))

    target_url = f"http://127.0.0.1:{cancel_server_port}/slow_stream.bin"

    async with async_session_factory() as session:
        import uuid
        user = User(email=f"cancel_test_{uuid.uuid4().hex[:6]}@example.com", hashed_password="pwd")
        session.add(user)
        await session.flush()

        src = Source(url=target_url, provider_id="direct_http", content_type="application/octet-stream", is_permitted=True)
        session.add(src)
        await session.flush()

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

    # Launch process_next_job in background task
    task = asyncio.create_task(worker.process_next_job(target_job_id=job_id))

    # Wait 0.15s until download starts, then cancel in DB
    await asyncio.sleep(0.15)
    async with async_session_factory() as session:
        j = await session.get(AcquisitionJob, job_id)
        if j:
            j.state = JobState.CANCELLED.value
            await session.commit()

    # Wait for worker execution to abort
    await task

    # Confirm job stayed CANCELLED and did NOT complete
    async with async_session_factory() as session:
        final_job = await session.get(AcquisitionJob, job_id)
        assert final_job.state == JobState.CANCELLED.value
        assert final_job.artifact_id is None
