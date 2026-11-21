from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from apps.api.app.models.database import get_db
from apps.api.app.models.entities import Source, SourceOption
from packages.shared_schemas.models import (
    SourceInspectionRequest,
    SourceInspectionResponse,
    FormatOption
)
from providers.registry import provider_registry

router = APIRouter(prefix="/sources", tags=["Sources"])

@router.post("/inspect", response_model=SourceInspectionResponse)
async def inspect_source(req: SourceInspectionRequest, db: AsyncSession = Depends(get_db)):
    url = req.url.strip()
    provider = provider_registry.find_provider_for_url(url)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No suitable provider registered to handle URL scheme/host: {url}"
        )

    inspection = await provider.inspect(url)

    # Persist or update Source in database
    stmt = select(Source).where(Source.url == url)
    res = await db.execute(stmt)
    existing_source = res.scalar_one_or_none()

    if existing_source:
        existing_source.content_type = inspection.mime_type
        existing_source.estimated_size_bytes = inspection.estimated_size_bytes
        existing_source.is_permitted = inspection.is_permitted
        existing_source.inspection_status = inspection.inspection_status
        source_id = existing_source.id
    else:
        new_source = Source(
            url=url,
            provider_id=provider.provider_id,
            content_type=inspection.mime_type,
            estimated_size_bytes=inspection.estimated_size_bytes,
            is_permitted=inspection.is_permitted,
            inspection_status=inspection.inspection_status
        )
        db.add(new_source)
        await db.flush()
        source_id = new_source.id

    # Refresh formats
    if inspection.is_permitted:
        formats = await provider.list_formats(url)
        for fmt in formats:
            stmt_opt = select(SourceOption).where(
                SourceOption.source_id == source_id,
                SourceOption.format_id == fmt.format_id
            )
            opt_res = await db.execute(stmt_opt)
            if not opt_res.scalar_one_or_none():
                db.add(SourceOption(
                    source_id=source_id,
                    format_id=fmt.format_id,
                    file_type=fmt.file_type,
                    mime_type=fmt.mime_type,
                    resolution=fmt.resolution,
                    codec=fmt.codec,
                    estimated_size_bytes=fmt.estimated_size_bytes,
                    quality_label=fmt.quality_label
                ))

    await db.commit()

    inspection.source_id = source_id
    return inspection

@router.get("/{source_id}/formats", response_model=List[FormatOption])
async def list_formats(source_id: str, db: AsyncSession = Depends(get_db)):
    source = await db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found.")

    stmt = select(SourceOption).where(SourceOption.source_id == source_id)
    res = await db.execute(stmt)
    options = res.scalars().all()

    return [
        FormatOption(
            format_id=opt.format_id,
            file_type=opt.file_type,
            mime_type=opt.mime_type,
            resolution=opt.resolution,
            codec=opt.codec,
            estimated_size_bytes=opt.estimated_size_bytes,
            quality_label=opt.quality_label
        )
        for opt in options
    ]
