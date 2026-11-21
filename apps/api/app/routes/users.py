import secrets
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any

from apps.api.app.models.database import get_db
from apps.api.app.models.entities import User, AcquisitionJob, Artifact, UserApproval
from apps.api.app.security.auth import get_authenticated_user_or_agent
from packages.shared_schemas.models import JobState, ApprovalStatus

router = APIRouter(prefix="/users", tags=["Users & Personal Dashboards"])

class PortalLinkRequest(BaseModel):
    email: Optional[str] = None
    name: Optional[str] = None

class UserProfileResponse(BaseModel):
    id: str
    email: str
    role: str
    portal_token: str
    dashboard_url: str
    active_jobs_count: int
    artifacts_count: int
    pending_approvals_count: int

class PortalLinkResponse(BaseModel):
    user_id: str
    email: str
    portal_token: str
    dashboard_url: str
    created: bool

def _format_dashboard_url(portal_token: str) -> str:
    # Default to standard frontend dashboard URL
    return f"http://localhost:5173/portal?token={portal_token}"

@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(
    user: User = Depends(get_authenticated_user_or_agent),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns current authenticated user details, persistent portal token,
    personal dashboard link, and real-time activity metrics.
    """
    if not user.portal_token:
        user.portal_token = f"aae_usr_{secrets.token_hex(20)}"
        await db.commit()
        await db.refresh(user)

    # Calculate active jobs count for this user
    active_states = [
        JobState.CREATED.value,
        JobState.UNDERSTANDING.value,
        JobState.DISCOVERING.value,
        JobState.INSPECTING.value,
        JobState.NEEDS_CLARIFICATION.value,
        JobState.AWAITING_APPROVAL.value,
        JobState.QUEUED.value,
        JobState.DOWNLOADING.value,
        JobState.VERIFYING.value
    ]
    stmt_jobs = select(func.count(AcquisitionJob.id)).where(
        AcquisitionJob.user_id == user.id,
        AcquisitionJob.state.in_(active_states)
    )
    res_jobs = await db.execute(stmt_jobs)
    active_jobs_count = res_jobs.scalar() or 0

    # Calculate artifacts count for this user
    stmt_arts = select(func.count(Artifact.id)).where(Artifact.user_id == user.id)
    res_arts = await db.execute(stmt_arts)
    artifacts_count = res_arts.scalar() or 0

    # Calculate pending approvals count for this user
    stmt_apprs = select(func.count(UserApproval.id)).where(
        UserApproval.user_id == user.id,
        UserApproval.status == ApprovalStatus.PENDING.value
    )
    res_apprs = await db.execute(stmt_apprs)
    pending_approvals_count = res_apprs.scalar() or 0

    return UserProfileResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        portal_token=user.portal_token,
        dashboard_url=_format_dashboard_url(user.portal_token),
        active_jobs_count=active_jobs_count,
        artifacts_count=artifacts_count,
        pending_approvals_count=pending_approvals_count
    )

@router.post("/portal-link", response_model=PortalLinkResponse)
async def get_or_create_portal_link(
    req: PortalLinkRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieves or generates a permanent personal dashboard link for any user.
    If an email is provided, finds the existing user or creates a new one.
    If no email is provided, provisions a fresh dedicated workspace user.
    """
    created = False
    if req.email:
        email = req.email.strip().lower()
        stmt = select(User).where(User.email == email)
        res = await db.execute(stmt)
        user = res.scalar_one_or_none()
        if not user:
            user = User(
                email=email,
                hashed_password=f"auto_{secrets.token_hex(16)}",
                role="user",
                portal_token=f"aae_usr_{secrets.token_hex(20)}"
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            created = True
        elif not user.portal_token:
            user.portal_token = f"aae_usr_{secrets.token_hex(20)}"
            await db.commit()
            await db.refresh(user)
    else:
        # Provision fresh dedicated workspace user
        new_email = f"user_{secrets.token_hex(4)}@antigravity.internal"
        user = User(
            email=new_email,
            hashed_password=f"auto_{secrets.token_hex(16)}",
            role="user",
            portal_token=f"aae_usr_{secrets.token_hex(20)}"
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        created = True

    return PortalLinkResponse(
        user_id=user.id,
        email=user.email,
        portal_token=user.portal_token,
        dashboard_url=_format_dashboard_url(user.portal_token),
        created=created
    )
