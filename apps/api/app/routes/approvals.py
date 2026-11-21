from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from pydantic import BaseModel

from apps.api.app.models.database import get_db
from apps.api.app.models.entities import UserApproval, Source, SourceOption, User
from packages.shared_schemas.models import (
    ApprovalRequestCreate,
    ApprovalResponse,
    ApprovalStatus
)

router = APIRouter(prefix="/approvals", tags=["Approvals"])

class ApprovalDecisionRequest(BaseModel):
    decision: ApprovalStatus # approved or rejected

@router.get("", response_model=list[ApprovalResponse])
async def list_approvals(db: AsyncSession = Depends(get_db)):
    stmt = select(UserApproval).order_by(UserApproval.created_at.desc()).limit(100)
    res = await db.execute(stmt)
    approvals = res.scalars().all()
    return [
        ApprovalResponse(
            approval_id=a.id,
            status=ApprovalStatus(a.status),
            message=a.reason or "Approval request",
            created_at=a.created_at
        )
        for a in approvals
    ]

@router.post("/request", response_model=ApprovalResponse)
async def request_approval(req: ApprovalRequestCreate, db: AsyncSession = Depends(get_db)):
    source = await db.get(Source, req.source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found.")

    stmt_user = select(User).limit(1)
    res_user = await db.execute(stmt_user)
    user = res_user.scalar_one_or_none()

    approval = UserApproval(
        user_id=user.id if user else "anonymous",
        source_id=req.source_id,
        format_id=req.format_id,
        status=ApprovalStatus.PENDING.value,
        reason=req.reason,
        estimated_size_bytes=source.estimated_size_bytes
    )
    db.add(approval)
    await db.commit()
    await db.refresh(approval)

    return ApprovalResponse(
        approval_id=approval.id,
        status=ApprovalStatus(approval.status),
        message="Approval request registered. Awaiting operator confirmation.",
        created_at=approval.created_at
    )

@router.get("/{approval_id}", response_model=ApprovalResponse)
async def get_approval(approval_id: str, db: AsyncSession = Depends(get_db)):
    approval = await db.get(UserApproval, approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found.")

    return ApprovalResponse(
        approval_id=approval.id,
        status=ApprovalStatus(approval.status),
        message=f"Current status: {approval.status}",
        created_at=approval.created_at
    )

@router.post("/{approval_id}/decision", response_model=ApprovalResponse)
async def decide_approval(approval_id: str, req: ApprovalDecisionRequest, db: AsyncSession = Depends(get_db)):
    approval = await db.get(UserApproval, approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found.")

    if approval.status != ApprovalStatus.PENDING.value:
        raise HTTPException(status_code=400, detail=f"Approval is already resolved with status '{approval.status}'.")

    approval.status = req.decision.value
    approval.decided_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(approval)

    return ApprovalResponse(
        approval_id=approval.id,
        status=ApprovalStatus(approval.status),
        message=f"Approval request marked as {approval.status}.",
        created_at=approval.created_at
    )
