from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel

from apps.api.app.models.database import get_db
from apps.api.app.models.entities import UserApproval, Source, SourceOption, User
from apps.api.app.security.auth import (
    require_permission,
    get_authenticated_portal_user,
    is_admin_request
)
from packages.shared_schemas.models import (
    ApprovalRequestCreate,
    ApprovalResponse,
    ApprovalStatus
)

router = APIRouter(prefix="/approvals", tags=["Approvals"])

class ApprovalDecisionRequest(BaseModel):
    decision: ApprovalStatus # approved or rejected

class ApprovalDetailResponse(BaseModel):
    approval_id: str
    source_id: str
    format_id: str
    status: ApprovalStatus
    reason: Optional[str] = None
    estimated_size_bytes: Optional[int] = None
    created_at: datetime

@router.get("", response_model=list[ApprovalDetailResponse])
async def list_approvals(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("read"))
):
    stmt = select(UserApproval)
    if not is_admin_request(request, user):
        stmt = stmt.where(UserApproval.user_id == user.id)
    stmt = stmt.order_by(UserApproval.created_at.desc()).limit(100)
    res = await db.execute(stmt)
    approvals = res.scalars().all()
    return [
        ApprovalDetailResponse(
            approval_id=a.id,
            source_id=a.source_id,
            format_id=a.format_id,
            status=ApprovalStatus(a.status),
            reason=a.reason,
            estimated_size_bytes=a.estimated_size_bytes,
            created_at=a.created_at
        )
        for a in approvals
    ]

@router.post("/request", response_model=ApprovalResponse)
async def request_approval(
    req: ApprovalRequestCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("acquire"))
):
    source = await db.get(Source, req.source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found.")
    if not source.is_permitted:
        raise HTTPException(status_code=403, detail="Acquisition from this source is forbidden by policy.")

    option_result = await db.execute(
        select(SourceOption).where(
            SourceOption.source_id == req.source_id,
            SourceOption.format_id == req.format_id
        )
    )
    option = option_result.scalar_one_or_none()
    if not option:
        raise HTTPException(status_code=404, detail="Format not found for source.")

    approval = UserApproval(
        user_id=user.id,
        source_id=req.source_id,
        format_id=req.format_id,
        status=ApprovalStatus.PENDING.value,
        reason=req.reason,
        estimated_size_bytes=option.estimated_size_bytes
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
async def get_approval(
    approval_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("read"))
):
    approval = await db.get(UserApproval, approval_id)
    if not approval or (not is_admin_request(request, user) and approval.user_id != user.id):
        raise HTTPException(status_code=404, detail="Approval request not found.")

    return ApprovalResponse(
        approval_id=approval.id,
        status=ApprovalStatus(approval.status),
        message=f"Current status: {approval.status}",
        created_at=approval.created_at
    )

@router.post("/{approval_id}/decision", response_model=ApprovalResponse)
async def decide_approval(
    approval_id: str,
    req: ApprovalDecisionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_authenticated_portal_user)
):
    approval = await db.get(UserApproval, approval_id)
    if not approval or (not is_admin_request(request, user) and approval.user_id != user.id):
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
