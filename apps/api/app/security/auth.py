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
    Authenticates requests using Bearer API keys ('aae_live_...')
    or falls back to the default operator user for local dashboard operations.
    """
    auth_header = request.headers.get("Authorization")

    if auth_header:
        parts = auth_header.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Malformed Authorization header. Format must be 'Bearer <token>'."
            )

        token = parts[1].strip()

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
            role="admin"
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return user
