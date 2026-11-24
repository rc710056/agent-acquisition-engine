import asyncio
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from sqlalchemy import select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession

class AcquisitionCancelledError(Exception):
    """Raised when an in-flight acquisition is aborted by operator or system request."""
    pass

class DownloadStalledError(Exception):
    """Raised when an in-flight acquisition stalls due to lack of progress or 0 bytes transferred."""
    pass

from apps.api.app.config import settings
from apps.api.app.models.database import async_session_factory, init_db
from apps.api.app.models.entities import (
    AcquisitionJob,
    JobEvent,
    Source,
    SourceOption,
    Artifact,
    UsageRecord
)
from packages.shared_schemas.models import JobState
from services.acquisition_worker.state_machine import validate_state_transition, InvalidStateTransitionError
from providers.registry import provider_registry
from apps.api.app.services.storage import storage_service

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger("aae.acquisition_worker")

class AcquisitionWorker:
    """
    Persistent background worker responsible for executing acquisition tasks,
    driving state machine transitions, reporting progress events, and verifying artifacts.
    """

    def __init__(self):
        self._is_running = False

    async def start(self) -> None:
        """Starts the worker daemon loop."""
        self._is_running = True
        logger.info("Acquisition Worker starting up...")
        await init_db()
        await self.recover_orphaned_jobs()

        while self._is_running:
            try:
                processed = await self.process_next_job()
                if not processed:
                    await asyncio.sleep(settings.WORKER_POLL_INTERVAL_SECONDS)
            except Exception as e:
                logger.error(f"Unexpected error in worker loop: {str(e)}", exc_info=True)
                await asyncio.sleep(settings.WORKER_POLL_INTERVAL_SECONDS)

    def stop(self) -> None:
        self._is_running = False
        logger.info("Acquisition Worker stopping...")

    async def recover_orphaned_jobs(self) -> None:
        """Recovers jobs that were interrupted by a previous worker crash/restart."""
        async with async_session_factory() as session:
            stmt = select(AcquisitionJob).where(
                AcquisitionJob.state.in_([JobState.DOWNLOADING.value, JobState.VERIFYING.value])
            )
            result = await session.execute(stmt)
            orphaned = result.scalars().all()

            for job in orphaned:
                logger.warning(f"Recovering orphaned job {job.id} found in state {job.state}")
                if job.retry_count < job.max_retries:
                    job.retry_count += 1
                    job.state = JobState.QUEUED.value
                    job.current_operation = f"Worker recovered after restart (retry #{job.retry_count})"
                    session.add(JobEvent(
                        job_id=job.id,
                        event_type="recovery",
                        message=f"Job recovered after worker restart. Retry #{job.retry_count} queued."
                    ))
                else:
                    job.state = JobState.FAILED.value
                    job.error_message = "Worker restarted and maximum retries were exhausted."
                    session.add(JobEvent(
                        job_id=job.id,
                        event_type="failure",
                        message="Worker restart exhausted retry budget."
                    ))
            await session.commit()

    async def process_next_job(self, target_job_id: Optional[str] = None) -> bool:
        """Pulls and executes the oldest eligible QUEUED job whose retry delay has elapsed."""
        now_utc = datetime.now(timezone.utc)
        async with async_session_factory() as session:
            stmt = select(AcquisitionJob).where(
                AcquisitionJob.state == JobState.QUEUED.value,
                or_(
                    AcquisitionJob.next_retry_at == None,
                    AcquisitionJob.next_retry_at <= now_utc
                )
            )
            if target_job_id:
                stmt = stmt.where(AcquisitionJob.id == target_job_id)
            else:
                stmt = stmt.order_by(AcquisitionJob.created_at.asc())

            stmt = stmt.limit(1)
            result = await session.execute(stmt)
            job = result.scalar_one_or_none()

            if not job:
                return False

            job_id = job.id
            source_id = job.source_id
            user_id = job.user_id
            format_id = job.format_id

            # Transition to DOWNLOADING
            validate_state_transition(job.state, JobState.DOWNLOADING)
            job.state = JobState.DOWNLOADING.value
            job.next_retry_at = None
            job.current_operation = "Connecting to source stream"
            session.add(JobEvent(
                job_id=job_id,
                event_type="state_change",
                message="Acquisition started by worker."
            ))
            await session.commit()

        # Execute download outside long-held session lock
        await self._execute_acquisition(job_id, source_id, user_id, format_id)
        return True

    async def _execute_acquisition(self, job_id: str, source_id: str, user_id: str, format_id: str) -> None:
        opt_file_type: Optional[str] = None
        opt_mime: Optional[str] = None
        async with async_session_factory() as session:
            stmt = select(Source).where(Source.id == source_id)
            res = await session.execute(stmt)
            source = res.scalar_one_or_none()
            if not source:
                await self._fail_job(job_id, f"Source reference {source_id} not found in database.")
                return
            target_url = source.canonical_url or source.url
            provider_id = source.provider_id

            stmt_opt = select(SourceOption).where(
                SourceOption.source_id == source_id,
                SourceOption.format_id == format_id
            )
            opt_res = await session.execute(stmt_opt)
            target_opt = opt_res.scalar_one_or_none()
            if target_opt:
                opt_file_type = target_opt.file_type
                opt_mime = target_opt.mime_type

        # 0. Check deduplication cache for existing verified artifact
        cache_key = hashlib.sha256(f"{target_url}::{format_id}".encode()).hexdigest()
        async with async_session_factory() as session:
            stmt = select(Artifact).where(
                Artifact.origin_cache_key == cache_key,
                Artifact.is_verified == True
            ).order_by(Artifact.created_at.desc()).limit(1)
            cached_art = (await session.execute(stmt)).scalar_one_or_none()
            if cached_art and opt_file_type == "video":
                if cached_art.mime_type.startswith("audio/") or cached_art.filename.lower().endswith((".m4a", ".mp3", ".aac")):
                    cached_art.is_verified = False
                    await session.commit()
                    cached_art = None

            if cached_art and storage_service.get_artifact_path(cached_art.storage_path).exists():
                job_record = await session.get(AcquisitionJob, job_id)
                if job_record:
                    if cached_art.user_id == user_id:
                        target_art_id = cached_art.id
                    else:
                        user_art = Artifact(
                            user_id=user_id,
                            filename=cached_art.filename,
                            mime_type=cached_art.mime_type,
                            size_bytes=cached_art.size_bytes,
                            sha256=cached_art.sha256,
                            storage_path=cached_art.storage_path,
                            is_verified=True,
                            origin_cache_key=cache_key
                        )
                        session.add(user_art)
                        await session.flush()
                        target_art_id = user_art.id

                    validate_state_transition(job_record.state, JobState.VERIFYING)
                    job_record.state = JobState.VERIFYING.value
                    validate_state_transition(job_record.state, JobState.COMPLETED)
                    job_record.state = JobState.COMPLETED.value
                    job_record.progress_percent = 100.0
                    job_record.bytes_transferred = cached_art.size_bytes
                    job_record.total_bytes = cached_art.size_bytes
                    job_record.current_operation = "Acquisition fulfilled instantly from deduplication cache"
                    job_record.artifact_id = target_art_id
                    session.add(JobEvent(
                        job_id=job_id,
                        event_type="completed",
                        message=f"Artifact {cached_art.filename} served from deduplication cache.",
                        payload={"cached": True, "artifact_id": target_art_id}
                    ))
                    await session.commit()
                    return

        provider = provider_registry.get_provider(provider_id)
        if not provider:
            await self._fail_job(job_id, f"Provider '{provider_id}' is not loaded or supported.")
            return

        temp_destination = storage_service.get_temp_path(prefix=f"job_{job_id[:8]}")
        start_time = datetime.now(timezone.utc)

        import time

        stall_timeout = getattr(settings, "DOWNLOAD_STALL_TIMEOUT_SECONDS", 60.0)
        last_progress_timestamp = time.time()
        transferred_bytes_count = 0
        last_progress_time = 0.0

        async def on_progress(transferred: int, total: Optional[int]) -> None:
            nonlocal last_progress_time, last_progress_timestamp, transferred_bytes_count
            now = time.time()
            if transferred > transferred_bytes_count or transferred > 0:
                transferred_bytes_count = transferred
                last_progress_timestamp = now

            if now - last_progress_time < 0.4:
                return  # Throttle DB writes
            last_progress_time = now

            pct = round((transferred / total) * 100, 2) if total and total > 0 else 0.0
            async with async_session_factory() as s:
                curr_job = await s.get(AcquisitionJob, job_id)
                if curr_job and curr_job.state == JobState.CANCELLED.value:
                    raise AcquisitionCancelledError(f"Acquisition for job {job_id} was aborted by operator cancellation.")

                await s.execute(
                    update(AcquisitionJob)
                    .where(AcquisitionJob.id == job_id)
                    .values(
                        bytes_transferred=transferred,
                        total_bytes=total,
                        progress_percent=pct,
                        current_operation=f"Downloading {transferred} bytes" + (f" of {total}" if total else "")
                    )
                )
                await s.commit()

        async def stall_watchdog(task: asyncio.Task):
            while not task.done():
                await asyncio.sleep(1.0)
                elapsed = time.time() - last_progress_timestamp
                if elapsed >= stall_timeout:
                    logger.warning(
                        f"Job {job_id} download stalled: {transferred_bytes_count} bytes transferred, "
                        f"no progress for {elapsed:.1f}s (threshold: {stall_timeout}s)."
                    )
                    task.cancel()
                    break

        try:
            # 1. Download stream with stall watchdog
            acquire_task = asyncio.create_task(
                provider.acquire(
                    url=target_url,
                    format_id=format_id,
                    destination_path=temp_destination,
                    progress_callback=on_progress,
                    timeout_seconds=settings.DEFAULT_DOWNLOAD_TIMEOUT_SECONDS,
                    max_size_bytes=settings.MAX_FILE_SIZE_BYTES
                )
            )
            watchdog_task = asyncio.create_task(stall_watchdog(acquire_task))

            try:
                acquire_result = await acquire_task
            except asyncio.CancelledError:
                elapsed = time.time() - last_progress_timestamp
                if elapsed >= stall_timeout:
                    reason = (
                        f"0 bytes transferred after {int(elapsed)} seconds"
                        if transferred_bytes_count == 0
                        else f"Stream stalled with no progress received for {int(elapsed)} seconds"
                    )
                    temp_destination.unlink(missing_ok=True)
                    logger.error(f"Job {job_id} failed due to download stall: {reason}")
                    await self._fail_job(job_id, f"Download timed out: {reason}")
                    return
                raise
            finally:
                watchdog_task.cancel()

            # 2. Transition to VERIFYING
            async with async_session_factory() as session:
                j = await session.get(AcquisitionJob, job_id)
                if j and j.state == JobState.CANCELLED.value:
                    temp_destination.unlink(missing_ok=True)
                    return
                if j:
                    validate_state_transition(j.state, JobState.VERIFYING)
                    j.state = JobState.VERIFYING.value
                    j.current_operation = "Running integrity verification & checksumming"
                    session.add(JobEvent(
                        job_id=job_id,
                        event_type="state_change",
                        message="File transfer completed. Running verification pipeline."
                    ))
                    await session.commit()

            # 3. Verify file
            verification = provider.verify(
                temp_destination,
                expected_size=acquire_result.get("total_bytes"),
                expected_sha256=acquire_result.get("sha256"),
                expected_mime=acquire_result.get("mime_type") or opt_mime,
                expected_file_type=opt_file_type
            )

            if not verification.is_valid:
                error_msg = "; ".join(verification.errors)
                temp_destination.unlink(missing_ok=True)
                await self._fail_job(job_id, f"File verification failed: {error_msg}")
                return

            # 4. Move to permanent storage
            final_filename = acquire_result.get("filename") or "download.bin"
            perm_path, clean_filename, size_bytes, sha256_hash = storage_service.store_artifact(
                temp_destination,
                final_filename
            )

            # 5. Extract rich media preview metadata (codecs, resolution, fps, bitrate)
            preview_meta = storage_service.extract_preview_metadata(perm_path, verification.detected_mime)

            # 6. Save Artifact and complete job
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            async with async_session_factory() as session:
                artifact = Artifact(
                    user_id=user_id,
                    filename=clean_filename,
                    mime_type=verification.detected_mime,
                    size_bytes=size_bytes,
                    sha256=sha256_hash,
                    storage_path=perm_path.name,
                    is_verified=True,
                    origin_cache_key=cache_key,
                    preview_metadata=preview_meta
                )
                session.add(artifact)
                await session.flush()

                job_record = await session.get(AcquisitionJob, job_id)
                if job_record:
                    validate_state_transition(job_record.state, JobState.COMPLETED)
                    job_record.state = JobState.COMPLETED.value
                    job_record.progress_percent = 100.0
                    job_record.bytes_transferred = size_bytes
                    job_record.total_bytes = size_bytes
                    job_record.current_operation = "Acquisition completed and verified"
                    job_record.artifact_id = artifact.id

                    session.add(JobEvent(
                        job_id=job_id,
                        event_type="completed",
                        message=f"Artifact {clean_filename} verified and stored. SHA-256: {sha256_hash[:16]}..."
                    ))

                    session.add(UsageRecord(
                        user_id=user_id,
                        job_id=job_id,
                        bytes_downloaded=size_bytes,
                        duration_seconds=duration
                    ))

                await session.commit()
                logger.info(f"Job {job_id} successfully completed. Artifact: {artifact.id}")

        except AcquisitionCancelledError as e:
            temp_destination.unlink(missing_ok=True)
            logger.info(f"Job {job_id} cancellation acknowledged during stream.")
            async with async_session_factory() as session:
                session.add(JobEvent(
                    job_id=job_id,
                    event_type="cancelled",
                    message="Download stream terminated upon operator cancellation."
                ))
                await session.commit()
        except Exception as e:
            temp_destination.unlink(missing_ok=True)
            logger.error(f"Error acquiring job {job_id}: {str(e)}", exc_info=True)
            await self._handle_job_error(job_id, str(e))

    async def _handle_job_error(self, job_id: str, error_message: str) -> None:
        async with async_session_factory() as session:
            job = await session.get(AcquisitionJob, job_id)
            if not job:
                return

            if job.retry_count < job.max_retries:
                job.retry_count += 1
                job.state = JobState.QUEUED.value
                # Exponential backoff: backoff_factor ^ retry_count seconds
                backoff_seconds = float(settings.RETRY_BACKOFF_FACTOR ** job.retry_count)
                job.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)
                job.current_operation = f"Retrying in {backoff_seconds:.1f}s (attempt #{job.retry_count}/{job.max_retries}): {error_message}"
                session.add(JobEvent(
                    job_id=job_id,
                    event_type="retry",
                    message=f"Retry #{job.retry_count} scheduled with {backoff_seconds:.1f}s backoff. Cause: {error_message}"
                ))
            else:
                job.state = JobState.FAILED.value
                job.error_message = error_message
                job.current_operation = "Failed: retries exhausted"
                session.add(JobEvent(
                    job_id=job_id,
                    event_type="failure",
                    message=f"Job permanently failed after {job.max_retries} attempts: {error_message}"
                ))
            await session.commit()

    async def _fail_job(self, job_id: str, error_message: str) -> None:
        async with async_session_factory() as session:
            job = await session.get(AcquisitionJob, job_id)
            if job:
                job.state = JobState.FAILED.value
                job.error_message = error_message
                job.current_operation = "Failed"
                session.add(JobEvent(
                    job_id=job_id,
                    event_type="failure",
                    message=error_message
                ))
                await session.commit()

if __name__ == "__main__":
    worker = AcquisitionWorker()
    try:
        asyncio.run(worker.start())
    except KeyboardInterrupt:
        worker.stop()
