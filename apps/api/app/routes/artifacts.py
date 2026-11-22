from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional

from apps.api.app.models.database import get_db
from apps.api.app.models.entities import Artifact, User
from packages.shared_schemas.models import ArtifactMetadata
from apps.api.app.services.storage import storage_service
from apps.api.app.security.tokens import verify_signed_delivery_token
from apps.api.app.security.auth import require_permission, is_admin_request
from apps.api.app.config import settings

router = APIRouter(tags=["Artifacts"])

def _get_request_base_url(request: Request) -> str:
    origin = request.headers.get("origin") or request.headers.get("x-forwarded-host")
    if origin:
        proto = request.headers.get("x-forwarded-proto", "https" if "trycloudflare" in origin else "http")
        return f"{proto}://{origin}".rstrip("/") if "://" not in origin else origin.rstrip("/")
    if request.base_url:
        return str(request.base_url).rstrip("/")
    return settings.API_BASE_URL.rstrip("/")

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

    req_base = _get_request_base_url(request)
    result = []
    for art in artifacts:
        bundle = storage_service.generate_delivery_bundle(art.id, base_url=req_base)
        result.append(ArtifactMetadata(
            artifact_id=art.id,
            filename=art.filename,
            mime_type=art.mime_type,
            size_bytes=art.size_bytes,
            sha256=art.sha256,
            is_verified=art.is_verified,
            download_url=bundle["download_url"],
            preview_url=bundle["preview_url"],
            contact_sheet_url=bundle["contact_sheet_url"] if art.mime_type.startswith("video/") else None,
            preview_metadata=art.preview_metadata,
            expires_at=bundle["expires_at"]
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

    req_base = _get_request_base_url(request)
    bundle = storage_service.generate_delivery_bundle(art.id, base_url=req_base)
    return ArtifactMetadata(
        artifact_id=art.id,
        filename=art.filename,
        mime_type=art.mime_type,
        size_bytes=art.size_bytes,
        sha256=art.sha256,
        is_verified=art.is_verified,
        download_url=bundle["download_url"],
        preview_url=bundle["preview_url"],
        contact_sheet_url=bundle["contact_sheet_url"] if art.mime_type.startswith("video/") else None,
        preview_metadata=art.preview_metadata,
        expires_at=bundle["expires_at"]
    )

@router.options("/delivery/download")
async def options_download_artifact_delivery():
    from fastapi.responses import Response
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Expose-Headers": "Content-Range, Accept-Ranges, Content-Length, Content-Disposition",
            "Access-Control-Max-Age": "86400",
        }
    )

@router.head("/delivery/download")
@router.get("/delivery/download")
async def download_artifact_delivery(
    token: str = Query(..., description="Cryptographically signed expiring token"),
    disposition: str = Query("attachment", description="'inline' for preview, 'attachment' for download"),
    view: Optional[str] = Query(None, description="Set to 'contact_sheet' to retrieve 2x2 contact sheet preview"),
    db: AsyncSession = Depends(get_db)
):
    """
    Validates signed token and streams verified artifact file.
    Does not expose internal storage paths or permanent links.
    Supports inline media playback, 2x2 contact sheet preview, and range requests.
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

    # Contact sheet preview mode
    if view == "contact_sheet":
        from pathlib import Path
        cs_name = f"{Path(file_path).stem}_contact_sheet.jpg"
        cs_path = storage_service.artifacts_dir / cs_name
        if not cs_path.exists() and art.mime_type.startswith("video/"):
            storage_service.generate_contact_sheet(file_path, output_filename=cs_name)
        if cs_path.exists():
            return FileResponse(
                path=cs_path,
                media_type="image/jpeg",
                content_disposition_type="inline",
                headers={
                    "Accept-Ranges": "bytes",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
                    "Access-Control-Allow-Headers": "*",
                    "Access-Control-Expose-Headers": "Content-Range, Accept-Ranges, Content-Length, Content-Disposition",
                    "Cache-Control": "public, max-age=86400"
                }
            )

    content_disp = "inline" if disposition == "inline" else "attachment"
    download_filename = art.filename or "download.bin"
    return FileResponse(
        path=file_path,
        media_type=art.mime_type or "application/octet-stream",
        filename=download_filename,
        content_disposition_type=content_disp,
        headers={
            "Accept-Ranges": "bytes",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Expose-Headers": "Content-Range, Accept-Ranges, Content-Length, Content-Disposition"
        }
    )
