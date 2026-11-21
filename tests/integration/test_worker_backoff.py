import pytest
from datetime import datetime, timezone
from apps.api.app.models.database import init_db, async_session_factory
from apps.api.app.models.entities import AcquisitionJob, User, Source
from packages.shared_schemas.models import JobState
from services.acquisition_worker.worker import AcquisitionWorker

@pytest.mark.asyncio
async def test_exponential_backoff_retry_scheduling():
    await init_db()

    async with async_session_factory() as session:
        import uuid
        user = User(email=f"backoff_test_{uuid.uuid4().hex[:6]}@example.com", hashed_password="pwd")
        session.add(user)
        await session.flush()

        src = Source(url="http://non-existent-host-999.invalid/file.pdf", provider_id="direct_http", is_permitted=True)
        session.add(src)
        await session.flush()

        job = AcquisitionJob(
            user_id=user.id,
            source_id=src.id,
            format_id="original",
            state=JobState.QUEUED.value,
            retry_count=0,
            max_retries=3
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    worker = AcquisitionWorker()

    # Simulate handling an error
    await worker._handle_job_error(job_id, "Simulated network timeout")

    async with async_session_factory() as session:
        j = await session.get(AcquisitionJob, job_id)
        assert j.state == JobState.QUEUED.value
        assert j.retry_count == 1
        assert j.next_retry_at is not None
        # Must be in the future
        now = datetime.now(timezone.utc)
        # Note: SQLite stores naive datetimes, compare naive or with timezone
        next_retry = j.next_retry_at.replace(tzinfo=timezone.utc) if j.next_retry_at.tzinfo is None else j.next_retry_at
        assert next_retry > now
