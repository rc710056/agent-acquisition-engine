import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional, Dict, Any

from apps.api.app.models.database import get_db
from apps.api.app.models.entities import Source, SourceOption, User
from packages.shared_schemas.models import (
    SourceInspectionRequest,
    SourceInspectionResponse,
    FormatOption,
    SourceType,
    SecurityStatus,
    AcquisitionPermission,
    SourceAccessStatus
)
from providers.registry import provider_registry
from apps.api.app.security.auth import require_permission

router = APIRouter(prefix="/sources", tags=["Sources"])

@router.post("/inspect", response_model=SourceInspectionResponse)
async def inspect_source(
    req: SourceInspectionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("read"))
):
    url = req.url.strip()

    provider, classification = await provider_registry.resolve_provider_with_classifier(url)

    if not provider:
        # Unsupported or restricted source
        inspection = SourceInspectionResponse(
            source_id=f"src_{uuid.uuid4().hex[:12]}",
            url=url,
            resolved_url=classification.resolved_url,
            source_type=classification.source_type,
            provider_id="unsupported",
            is_permitted=False,
            security_status=classification.security_status,
            acquisition_permission=classification.acquisition_permission,
            source_access_status=classification.source_access_status,
            capabilities=[],
            mime_type=classification.mime_type,
            estimated_size_bytes=classification.estimated_size_bytes,
            inspection_status="unsupported",
            title=classification.title,
            errors=classification.errors or [f"No provider found capable of acquiring source: {url}"]
        )
    else:
        inspection = await provider.inspect(url)
        # Ensure classification metadata is enriched if provider didn't populate it
        if not inspection.resolved_url:
            inspection.resolved_url = classification.resolved_url
        if inspection.source_type == SourceType.DIRECT_FILE and classification.source_type != SourceType.DIRECT_FILE:
            inspection.source_type = classification.source_type

    # Calculate advance approval gate visibility (Gap 2.7)
    if inspection.is_permitted:
        calc_size = inspection.estimated_size_bytes
        if calc_size is None and inspection.formats:
            calc_size = inspection.formats[0].estimated_size_bytes

        if calc_size is None:
            inspection.requires_approval = True
            inspection.approval_reason = "File size is unknown. Operator approval required before acquisition."
        elif calc_size > 52_428_800:
            inspection.requires_approval = True
            inspection.approval_reason = f"Estimated file size ({calc_size} bytes) exceeds 50 MB threshold. Operator approval required."
        else:
            inspection.requires_approval = False
            inspection.approval_reason = None
    else:
        inspection.requires_approval = False
        inspection.approval_reason = None

    # Persist or update Source in database
    stmt = select(Source).where(Source.url == url)
    res = await db.execute(stmt)
    existing_source = res.scalar_one_or_none()

    assets_data = [a.model_dump() for a in inspection.assets] if inspection.assets else None

    if existing_source:
        existing_source.canonical_url = inspection.resolved_url
        existing_source.source_type = inspection.source_type.value
        existing_source.provider_id = inspection.provider_id
        existing_source.content_type = inspection.mime_type
        existing_source.estimated_size_bytes = inspection.estimated_size_bytes
        existing_source.is_permitted = inspection.is_permitted
        existing_source.security_status = inspection.security_status.value
        existing_source.acquisition_permission = inspection.acquisition_permission.value
        existing_source.source_access_status = inspection.source_access_status.value
        existing_source.title = inspection.title
        existing_source.thumbnail_url = inspection.thumbnail_url
        existing_source.assets_metadata = assets_data
        existing_source.inspection_status = inspection.inspection_status
        source_id = existing_source.id
    else:
        new_source = Source(
            url=url,
            canonical_url=inspection.resolved_url,
            source_type=inspection.source_type.value,
            provider_id=inspection.provider_id,
            content_type=inspection.mime_type,
            estimated_size_bytes=inspection.estimated_size_bytes,
            is_permitted=inspection.is_permitted,
            security_status=inspection.security_status.value,
            acquisition_permission=inspection.acquisition_permission.value,
            source_access_status=inspection.source_access_status.value,
            title=inspection.title,
            thumbnail_url=inspection.thumbnail_url,
            assets_metadata=assets_data,
            inspection_status=inspection.inspection_status
        )
        db.add(new_source)
        await db.flush()
        source_id = new_source.id

    # Refresh formats (purge previous stale format options for this source)
    if inspection.is_permitted and provider:
        formats = inspection.formats or await provider.list_formats(url)
        from sqlalchemy import delete
        await db.execute(delete(SourceOption).where(SourceOption.source_id == source_id))
        for fmt in formats:
            db.add(SourceOption(
                source_id=source_id,
                format_id=fmt.format_id,
                file_type=fmt.file_type,
                mime_type=fmt.mime_type,
                resolution=fmt.resolution,
                codec=fmt.codec,
                estimated_size_bytes=fmt.estimated_size_bytes,
                quality_label=fmt.quality_label,
                download_url=fmt.download_url,
                has_audio=fmt.has_audio,
                has_video=fmt.has_video,
                category=fmt.category
            ))

    await db.commit()

    inspection.source_id = source_id
    return inspection

@router.get("/search")
async def search_sources(
    query: str = Query(..., min_length=1, description="Natural language title, keyword, or topic to search for"),
    kind: Optional[str] = Query(None, description="Optional filter: 'movie', 'video', 'audio', 'document', 'archive'"),
    limit: int = Query(5, ge=1, le=10, description="Maximum candidate results to return"),
    user: User = Depends(require_permission("read"))
):
    from services.mcp_server.server import search_sources as mcp_search_sources
    res = await mcp_search_sources(query=query, kind=kind, max_results=limit)
    return res

@router.get("/{source_id}/formats", response_model=List[FormatOption])
async def list_formats(
    source_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("read"))
):
    source = await db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found.")

    stmt = select(SourceOption).where(SourceOption.source_id == source_id)
    res = await db.execute(stmt)
    options = res.scalars().all()

    converted = [
        FormatOption(
            format_id=opt.format_id,
            file_type=opt.file_type,
            mime_type=opt.mime_type,
            resolution=opt.resolution,
            codec=opt.codec,
            estimated_size_bytes=opt.estimated_size_bytes,
            quality_label=opt.quality_label,
            download_url=opt.download_url,
            has_audio=opt.has_audio,
            has_video=opt.has_video,
            category=opt.category
        )
        for opt in options
    ]

    # Prioritize: best_video_audio first, then recommended, then audio_only, then others
    def sort_key(f: FormatOption):
        if f.format_id == "best_video_audio":
            return (0, 0)
        if f.category == "recommended" or (f.has_audio is not False and f.file_type == "video"):
            return (1, 0)
        if f.category == "audio_only" or f.file_type == "audio":
            return (2, 0)
        return (3, 0)

    return sorted(converted, key=sort_key)
