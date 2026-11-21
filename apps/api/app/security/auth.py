import secrets
from fastapi import Request, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from typing import Optional

from apps.api.app.models.database import get_db
from apps.api.app.models.entities import User, AgentConnection
from apps.api.app.security.tokens import hash_api_key

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
                return user

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unrecognized token format or invalid authentication credentials."
        )

    # Local development / dashboard fallback
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

    return user
