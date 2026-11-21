from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from datetime import datetime, timezone

from apps.api.app.models.database import get_db
from apps.api.app.models.entities import (
    Source,
    SourceOption,
    AcquisitionJob,
    UserApproval,
    Artifact,
    User
)
from packages.shared_schemas.models import (
    PreflightRequest,
    PreflightResponse,
    CreateJobRequest,
    JobStatusResponse,
    JobState,
    ApprovalStatus
)
from services.acquisition_worker.state_machine import validate_state_transition

from apps.api.app.security.auth import get_authenticated_user_or_agent

router = APIRouter(prefix="/acquisitions", tags=["Acquisitions"])

# Default mock user helper for MVP
async def get_or_create_default_user(db: AsyncSession) -> User:
    stmt = select(User).limit(1)
    res = await db.execute(stmt)
    u = res.scalar_one_or_none()
    if not u:
        u = User(email="operator@antigravity.internal", hashed_password="default_pwd_hash", role="admin")
        db.add(u)
        await db.flush()
    return u

@router.post("/preflight", response_model=PreflightResponse)
async def preflight_acquisition(req: PreflightRequest, db: AsyncSession = Depends(get_db)):
    source = await db.get(Source, req.source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found.")

    if not source.is_permitted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acquisition from this source is forbidden by policy or access controls."
        )

    if not source.is_permitted:
        return PreflightResponse(
            can_acquire=False,
            requires_approval=False,
            approval_reason="Acquisition from this source is forbidden by policy.",
            estimated_size_bytes=source.estimated_size_bytes,
            storage_available=True,
            duplicate_artifact_id=None
        )

    # Check format
    stmt_opt = select(SourceOption).where(
        SourceOption.source_id == req.source_id,
        SourceOption.format_id == req.format_id
    )
    res = await db.execute(stmt_opt)
    opt = res.scalar_one_or_none()
    if not opt:
        raise HTTPException(status_code=404, detail=f"Format '{req.format_id}' not found for source.")

    # High size (> 50 MB) requires approval
    requires_approval = False
    approval_reason = None
    if opt.estimated_size_bytes and opt.estimated_size_bytes > 52_428_800:
        requires_approval = True
        approval_reason = f"Estimated file size ({opt.estimated_size_bytes} bytes) exceeds 50 MB threshold. Operator approval required."

    # Check for existing completed duplicate artifact
    stmt_dup = (
        select(Artifact)
        .join(AcquisitionJob, AcquisitionJob.artifact_id == Artifact.id)
        .where(
            AcquisitionJob.source_id == req.source_id,
            AcquisitionJob.format_id == req.format_id,
            AcquisitionJob.state == JobState.COMPLETED.value,
            Artifact.is_verified == True
        )
        .limit(1)
    )
    dup_res = await db.execute(stmt_dup)
    duplicate_art = dup_res.scalar_one_or_none()

    return PreflightResponse(
        can_acquire=True,
        requires_approval=requires_approval,
        approval_reason=approval_reason,
        estimated_size_bytes=opt.estimated_size_bytes,
        storage_available=True,
        duplicate_artifact_id=duplicate_art.id if duplicate_art else None
    )

@router.post("/jobs", response_model=JobStatusResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    req: CreateJobRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_authenticated_user_or_agent)
):
    source = await db.get(Source, req.source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found.")

    if not source.is_permitted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acquisition from this source is forbidden by policy or access controls."
        )

    # Validate format and check if approval is required
    stmt_opt = select(SourceOption).where(
        SourceOption.source_id == req.source_id,
        SourceOption.format_id == req.format_id
    )
    res_opt = await db.execute(stmt_opt)
    opt = res_opt.scalar_one_or_none()
    if not opt:
        raise HTTPException(status_code=404, detail=f"Format '{req.format_id}' not found for source.")

    needs_approval = (opt.estimated_size_bytes and opt.estimated_size_bytes > 52_428_800)
    if needs_approval and not req.approval_id:
        if req.auto_approve:
            # Authenticated operator pre-approved the large acquisition
            now = datetime.now(timezone.utc)
            approval = UserApproval(
                user_id=user.id,
                source_id=req.source_id,
                format_id=req.format_id,
                status=ApprovalStatus.APPROVED.value,
                reason="Direct operator authorization via Workspace dispatch.",
                estimated_size_bytes=opt.estimated_size_bytes,
                decided_at=now,
                created_at=now
            )
            db.add(approval)
            await db.flush()
            req.approval_id = approval.id
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operator approval is required (estimated size > 50 MB), but approval_id was not provided."
            )

    # If approval requested/needed, check approval status
    if req.approval_id:
        approval = await db.get(UserApproval, req.approval_id)
        if not approval:
            raise HTTPException(status_code=400, detail="Specified approval ID does not exist.")
        if approval.status != ApprovalStatus.APPROVED.value:
            raise HTTPException(status_code=403, detail=f"Approval request is '{approval.status}', not approved.")

    # Duplicate prevention: check if identical active job is already queued or downloading
    stmt_active = select(AcquisitionJob).where(
        AcquisitionJob.user_id == user.id,
        AcquisitionJob.source_id == req.source_id,
        AcquisitionJob.format_id == req.format_id,
        AcquisitionJob.state.in_([JobState.QUEUED.value, JobState.DOWNLOADING.value])
    ).limit(1)
    res_active = await db.execute(stmt_active)
    active_job = res_active.scalar_one_or_none()
    if active_job:
        return JobStatusResponse(
            job_id=active_job.id,
            state=JobState(active_job.state),
            progress_percent=active_job.progress_percent,
            bytes_transferred=active_job.bytes_transferred,
            total_bytes=active_job.total_bytes,
            current_operation=active_job.current_operation,
            artifact_id=active_job.artifact_id,
            error_message=active_job.error_message,
            created_at=active_job.created_at,
            updated_at=active_job.updated_at
        )

    job = AcquisitionJob(
        user_id=user.id,
        source_id=req.source_id,
        format_id=req.format_id,
        execution_mode=req.execution_mode.value,
        state=JobState.QUEUED.value,
        current_operation="Queued for worker execution"
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    return JobStatusResponse(
        job_id=job.id,
        state=JobState(job.state),
        progress_percent=job.progress_percent,
        bytes_transferred=job.bytes_transferred,
        total_bytes=job.total_bytes,
        current_operation=job.current_operation,
        artifact_id=job.artifact_id,
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at
    )

@router.get("/jobs", response_model=List[JobStatusResponse])
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_authenticated_user_or_agent)
):
    stmt = select(AcquisitionJob)
    if user.role != "admin":
        stmt = stmt.where(AcquisitionJob.user_id == user.id)
    stmt = stmt.order_by(AcquisitionJob.created_at.desc()).limit(100)
    res = await db.execute(stmt)
    jobs = res.scalars().all()
    return [
        JobStatusResponse(
            job_id=j.id,
            state=JobState(j.state),
            progress_percent=j.progress_percent,
            bytes_transferred=j.bytes_transferred,
            total_bytes=j.total_bytes,
            current_operation=j.current_operation,
            artifact_id=j.artifact_id,
            error_message=j.error_message,
            created_at=j.created_at,
            updated_at=j.updated_at
        )
        for j in jobs
    ]

@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_authenticated_user_or_agent)
):
    job = await db.get(AcquisitionJob, job_id)
    if not job or (user.role != "admin" and job.user_id != user.id):
        raise HTTPException(status_code=404, detail="Job not found.")

    return JobStatusResponse(
        job_id=job.id,
        state=JobState(job.state),
        progress_percent=job.progress_percent,
        bytes_transferred=job.bytes_transferred,
        total_bytes=job.total_bytes,
        current_operation=job.current_operation,
        artifact_id=job.artifact_id,
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at
    )

@router.post("/jobs/{job_id}/cancel", response_model=JobStatusResponse)
async def cancel_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_authenticated_user_or_agent)
):
    job = await db.get(AcquisitionJob, job_id)
    if not job or (user.role != "admin" and job.user_id != user.id):
        raise HTTPException(status_code=404, detail="Job not found.")

    if job.state in [JobState.COMPLETED.value, JobState.FAILED.value, JobState.CANCELLED.value]:
        raise HTTPException(status_code=400, detail=f"Cannot cancel job in terminal state '{job.state}'.")

    validate_state_transition(job.state, JobState.CANCELLED)
    job.state = JobState.CANCELLED.value
    job.current_operation = "Cancelled by user request"
    await db.commit()
    await db.refresh(job)

    return JobStatusResponse(
        job_id=job.id,
        state=JobState(job.state),
        progress_percent=job.progress_percent,
        bytes_transferred=job.bytes_transferred,
        total_bytes=job.total_bytes,
        current_operation=job.current_operation,
        artifact_id=job.artifact_id,
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at
    )
