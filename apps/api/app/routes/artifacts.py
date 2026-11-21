from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from apps.api.app.models.database import get_db
from apps.api.app.models.entities import Artifact, User
from packages.shared_schemas.models import ArtifactMetadata
from apps.api.app.services.storage import storage_service
from apps.api.app.security.tokens import verify_signed_delivery_token
from apps.api.app.security.auth import require_permission, is_admin_request
from apps.api.app.config import settings

router = APIRouter(tags=["Artifacts"])

@router.get("/artifacts", response_model=List[ArtifactMetadata])
async def list_artifacts(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("read"))
):
    stmt = select(Artifact).where(Artifact.is_verified == True)
    if not is_admin_request(request, user):
        stmt = stmt.where(Artifact.user_id == user.id)
    stmt = stmt.order_by(Artifact.created_at.desc()).limit(100)
    res = await db.execute(stmt)
    artifacts = res.scalars().all()

    result = []
    for art in artifacts:
        dl_url, exp_time = storage_service.generate_delivery_url(art.id)
        result.append(ArtifactMetadata(
            artifact_id=art.id,
            filename=art.filename,
            mime_type=art.mime_type,
            size_bytes=art.size_bytes,
            sha256=art.sha256,
            is_verified=art.is_verified,
            download_url=dl_url,
            expires_at=exp_time
        ))
    return result

@router.get("/artifacts/{artifact_id}", response_model=ArtifactMetadata)
async def get_artifact(
    artifact_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("read"))
):
    art = await db.get(Artifact, artifact_id)
    if not art or not art.is_verified or (not is_admin_request(request, user) and art.user_id != user.id):
        raise HTTPException(status_code=404, detail="Artifact not found.")

    dl_url, exp_time = storage_service.generate_delivery_url(art.id)
    return ArtifactMetadata(
        artifact_id=art.id,
        filename=art.filename,
        mime_type=art.mime_type,
        size_bytes=art.size_bytes,
        sha256=art.sha256,
        is_verified=art.is_verified,
        download_url=dl_url,
        expires_at=exp_time
    )

@router.get("/delivery/download")
async def download_artifact_delivery(token: str = Query(..., description="Cryptographically signed expiring token"), db: AsyncSession = Depends(get_db)):
    """
    Validates signed token and streams verified artifact file.
    Does not expose internal storage paths or permanent links.
    """
    is_valid, artifact_id, error_reason = verify_signed_delivery_token(token, settings.SECRET_KEY)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: {error_reason or 'Invalid or expired delivery token'}"
        )

    art = await db.get(Artifact, artifact_id)
    if not art or not art.is_verified:
        raise HTTPException(status_code=404, detail="Requested artifact does not exist.")

    file_path = storage_service.get_artifact_path(art.storage_path)
    if not file_path:
        raise HTTPException(status_code=404, detail="Artifact file payload is missing from storage.")

    return FileResponse(
        path=file_path,
        media_type=art.mime_type,
        filename=art.filename
    )
