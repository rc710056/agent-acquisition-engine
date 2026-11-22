import asyncio
import pytest
from datetime import datetime, timezone
from apps.api.app.models.database import async_session_factory, init_db
from apps.api.app.models.entities import AcquisitionJob, Source, SourceOption, User
from packages.shared_schemas.models import JobState
from services.acquisition_worker.worker import AcquisitionWorker
from packages.provider_contracts.base import BaseProviderContract
from providers.registry import provider_registry

class StalledDummyProvider(BaseProviderContract):
    provider_id = "stalled_dummy"
    display_name = "Stalled Dummy Provider"

    def can_handle(self, url: str) -> bool:
        return "stalled-test" in url

    async def inspect(self, url: str):
        pass

    async def list_formats(self, url: str):
        return []

    async def check_permissions(self, url: str):
        return True, []

    async def acquire(self, url, format_id, destination_path, progress_callback=None, timeout_seconds=300, max_size_bytes=524288000):
        # Simulate stall by sleeping indefinitely without calling progress callback
        await asyncio.sleep(100)
        return {}

    def verify(self, file_path, **kwargs):
        pass

@pytest.mark.asyncio
async def test_worker_stall_detection(monkeypatch, tmp_path):
    await init_db()
    worker = AcquisitionWorker()

    stalled_provider = StalledDummyProvider()
    monkeypatch.setattr(provider_registry, "get_provider", lambda pid: stalled_provider)

    from apps.api.app.config import settings
    # Set short stall timeout for test
    monkeypatch.setattr(settings, "DOWNLOAD_STALL_TIMEOUT_SECONDS", 1.5)

    import uuid
    uid = uuid.uuid4().hex[:8]
    job_id = f"job_stall_{uid}"
    source_id = f"src_stall_{uid}"
    user_id = "user_default"

    async with async_session_factory() as session:
        # Create source and job
        src = Source(
            id=source_id,
            url="https://stalled-test.org/stream",
            provider_id="stalled_dummy",
            source_type="DIRECT_FILE",
            is_permitted=True,
            content_type="video/mp4"
        )
        job = AcquisitionJob(
            id=job_id,
            user_id=user_id,
            source_id=source_id,
            format_id="original",
            state=JobState.QUEUED.value
        )
        session.add(src)
        session.add(job)
        await session.commit()

    # Process job
    await worker.process_next_job(target_job_id=job_id)

    # Verify job failed cleanly due to stall
    async with async_session_factory() as session:
        j = await session.get(AcquisitionJob, job_id)
        assert j.state == JobState.FAILED.value
        assert "stall" in j.error_message.lower() or "timed out" in j.error_message.lower()
