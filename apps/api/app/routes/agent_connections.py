import secrets
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime

from apps.api.app.models.database import get_db
from apps.api.app.models.entities import AgentConnection, User
from apps.api.app.security.tokens import hash_api_key
from apps.api.app.security.auth import get_authenticated_portal_user, require_permission, is_admin_request

router = APIRouter(prefix="/connections", tags=["Agent Connections"])

class CreateConnectionRequest(BaseModel):
    agent_name: str
    permissions: List[str] = Field(default_factory=lambda: ["read", "acquire"])

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, permissions: List[str]) -> List[str]:
        if not permissions or "read" not in permissions or not set(permissions).issubset({"read", "acquire"}):
            raise ValueError("Agent permissions must include 'read' and may only include 'acquire'.")
        return permissions

class ConnectionResponse(BaseModel):
    id: str
    agent_name: str
    api_key: Optional[str] = None # Returned only once upon creation
    permissions: List[str]
    last_active_at: Optional[datetime] = None
    created_at: datetime

@router.post("", response_model=ConnectionResponse, status_code=status.HTTP_201_CREATED)
async def create_agent_connection(
    req: CreateConnectionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_authenticated_portal_user)
):
    raw_api_key = f"aae_live_{secrets.token_urlsafe(32)}"
    hashed_key = hash_api_key(raw_api_key)

    conn = AgentConnection(
        user_id=user.id,
        agent_name=req.agent_name,
        api_key_hash=hashed_key,
        permissions=req.permissions
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)

    return ConnectionResponse(
        id=conn.id,
        agent_name=conn.agent_name,
        api_key=raw_api_key,
        permissions=conn.permissions or [],
        last_active_at=conn.last_active_at,
        created_at=conn.created_at
    )

@router.get("", response_model=List[ConnectionResponse])
async def list_agent_connections(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("read"))
):
    stmt = select(AgentConnection)
    if not is_admin_request(request, user):
        stmt = stmt.where(AgentConnection.user_id == user.id)
    stmt = stmt.order_by(AgentConnection.created_at.desc())
    res = await db.execute(stmt)
    conns = res.scalars().all()
    return [
        ConnectionResponse(
            id=c.id,
            agent_name=c.agent_name,
            api_key=None,
            permissions=c.permissions or [],
            last_active_at=c.last_active_at,
            created_at=c.created_at
        )
        for c in conns
    ]

@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_agent_connection(
    connection_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_authenticated_portal_user)
):
    conn = await db.get(AgentConnection, connection_id)
    if not conn or (user.role != "admin" and conn.user_id != user.id):
        raise HTTPException(status_code=404, detail="Connection not found.")
    await db.delete(conn)
    await db.commit()
