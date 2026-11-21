import pytest
import uvicorn
import asyncio
import uuid
from pathlib import Path
from fastapi import FastAPI, Response
from apps.api.app.models.database import init_db, async_session_factory
from apps.api.app.models.entities import User, Source, AcquisitionJob, JobEvent, Artifact
from packages.shared_schemas.models import JobState
from services.acquisition_worker.worker import AcquisitionWorker
from services.acquisition_worker.state_machine import validate_state_transition, InvalidStateTransitionError

# Mock server app
worker_test_app = FastAPI()
SAMPLE_PAYLOAD = b"%PDF-1.5 Verified worker test artifact"

@worker_test_app.head("/sample.pdf")
async def mock_head():
    return Response(
        content=b"",
        headers={
            "Content-Type": "application/pdf",
            "Content-Length": str(len(SAMPLE_PAYLOAD)),
            "Content-Disposition": 'attachment; filename="worker_sample.pdf"'
        }
    )

@worker_test_app.get("/sample.pdf")
async def mock_get():
    return Response(
        content=SAMPLE_PAYLOAD,
        headers={
            "Content-Type": "application/pdf",
            "Content-Length": str(len(SAMPLE_PAYLOAD)),
            "Content-Disposition": 'attachment; filename="worker_sample.pdf"'
        }
    )

@pytest.fixture(scope="module")
def worker_server_port():
    return 8998

@pytest.fixture(scope="module", autouse=True)
def run_worker_mock_server(worker_server_port):
    config = uvicorn.Config(worker_test_app, host="127.0.0.1", port=worker_server_port, log_level="warning")
    server = uvicorn.Server(config)

    loop = asyncio.new_event_loop()
    import threading
    thread = threading.Thread(target=lambda: loop.run_until_complete(server.serve()), daemon=True)
    thread.start()

    import time
    time.sleep(0.5)
    yield
    server.should_exit = True

def test_state_machine_validation():
    # Valid transitions
    assert validate_state_transition(JobState.CREATED, JobState.QUEUED) is True
    assert validate_state_transition(JobState.QUEUED, JobState.DOWNLOADING) is True
    assert validate_state_transition(JobState.DOWNLOADING, JobState.VERIFYING) is True
    assert validate_state_transition(JobState.VERIFYING, JobState.COMPLETED) is True

    # Invalid transitions
    with pytest.raises(InvalidStateTransitionError):
        validate_state_transition(JobState.CREATED, JobState.COMPLETED)

    with pytest.raises(InvalidStateTransitionError):
        validate_state_transition(JobState.COMPLETED, JobState.DOWNLOADING)

@pytest.mark.asyncio
async def test_worker_end_to_end_job_processing(worker_server_port, monkeypatch):
    await init_db()

    from apps.api.app.security.ssrf import SSRFValidator
    monkeypatch.setattr(SSRFValidator, "validate_url", lambda url: (True, None))

    target_url = f"http://127.0.0.1:{worker_server_port}/sample.pdf"

    async with async_session_factory() as session:
        # Create user
        user = User(email=f"worker_test_{uuid.uuid4().hex[:6]}@example.com", hashed_password="pwd")
        session.add(user)
        await session.flush()

        # Create source
        source = Source(
            url=target_url,
            provider_id="direct_http",
            content_type="application/pdf",
            estimated_size_bytes=len(SAMPLE_PAYLOAD),
            is_permitted=True
        )
        session.add(source)
        await session.flush()

        # Create queued job
        job = AcquisitionJob(
            user_id=user.id,
            source_id=source.id,
            format_id="original",
            state=JobState.QUEUED.value
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    worker = AcquisitionWorker()
    processed = await worker.process_next_job()
    assert processed is True

    # Verify final state in database
    async with async_session_factory() as session:
        completed_job = await session.get(AcquisitionJob, job_id)
        assert completed_job.state == JobState.COMPLETED.value
        assert completed_job.progress_percent == 100.0
        assert completed_job.artifact_id is not None

        artifact = await session.get(Artifact, completed_job.artifact_id)
        assert artifact is not None
        assert artifact.filename == "worker_sample.pdf"
        assert artifact.size_bytes == len(SAMPLE_PAYLOAD)
        assert artifact.is_verified is True
