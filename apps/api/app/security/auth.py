import secrets
from fastapi import Request, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone

from apps.api.app.models.database import get_db
from apps.api.app.models.entities import User, AgentConnection
from apps.api.app.security.tokens import hash_api_key
from apps.api.app.config import settings

async def get_authenticated_user_or_agent(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Authenticates requests using:
    1. Bearer API keys ('aae_live_...') for connected AI agents.
    2. User Personal Dashboard Portal tokens ('aae_usr_...') via Bearer or '?token=' query parameter.
    3. Fallback to default operator user for local development.
    """
    auth_header = request.headers.get("Authorization")
    query_token = request.query_params.get("token") or request.query_params.get("user_key")

    token = None
    if auth_header:
        parts = auth_header.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1].strip()
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Malformed Authorization header. Format must be 'Bearer <token>'."
            )
    elif query_token:
        token = query_token.strip()
        if token.startswith("aae_live_"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Agent API keys must be sent in the Authorization header."
            )

    if token:
        # Check if it's a personal user dashboard portal token
        if token.startswith("aae_usr_"):
            stmt = select(User).where(User.portal_token == token)
            res = await db.execute(stmt)
            user = res.scalar_one_or_none()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired personal dashboard link token."
                )
            request.state.auth_kind = "portal"
            request.state.permissions = {"read", "acquire", "approve"}
            return user

        # Check if it's an agent API key
        if token.startswith("aae_live_"):
            hashed = hash_api_key(token)
            stmt = select(AgentConnection).where(AgentConnection.api_key_hash == hashed)
            res = await db.execute(stmt)
            conn = res.scalar_one_or_none()
            if not conn:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or revoked agent API key."
                )

            # Update last activity timestamp
            conn.last_active_at = datetime.now(timezone.utc)
            await db.commit()

            user = await db.get(User, conn.user_id)
            if user:
                request.state.auth_kind = "agent"
                request.state.permissions = set(conn.permissions or []) & {"read", "acquire"}
                return user

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unrecognized token format or invalid authentication credentials."
        )

    if settings.ENVIRONMENT.lower() not in {"development", "dev", "test"}:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required."
        )

    # Local development fallback
    stmt = select(User).limit(1)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        user = User(
            email="operator@antigravity.internal",
            hashed_password="local_operator_hash",
            role="admin",
            portal_token=f"aae_usr_{secrets.token_hex(20)}"
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    elif not user.portal_token:
        user.portal_token = f"aae_usr_{secrets.token_hex(20)}"
        await db.commit()
        await db.refresh(user)

    request.state.auth_kind = "development"
    request.state.permissions = {"read", "acquire", "approve"}
    return user

def require_permission(permission: str):
    async def dependency(
        request: Request,
        user: User = Depends(get_authenticated_user_or_agent)
    ) -> User:
        if permission not in getattr(request.state, "permissions", set()):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"The authenticated credential does not have the '{permission}' permission."
            )
        return user

    return dependency

def is_admin_request(request: Request, user: User) -> bool:
    return (
        user.role == "admin"
        and getattr(request.state, "auth_kind", None) in {"portal", "development"}
    )

async def get_authenticated_portal_user(
    request: Request,
    user: User = Depends(get_authenticated_user_or_agent)
) -> User:
    if getattr(request.state, "auth_kind", None) == "agent":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A user portal credential is required for this action."
        )
    return user
