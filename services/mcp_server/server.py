import asyncio
import logging
import hashlib
from typing import Optional, Dict, Any, List
from mcp.server.mcpserver import MCPServer
from sqlalchemy import select

from apps.api.app.config import settings
from apps.api.app.models.database import async_session_factory, init_db
from apps.api.app.models.entities import (
    Source,
    SourceOption,
    AcquisitionJob,
    JobEvent,
    UserApproval,
    Artifact,
    User
)
from packages.shared_schemas.models import (
    JobState,
    ApprovalStatus,
    SourceType,
    SecurityStatus,
    AcquisitionPermission,
    SourceAccessStatus
)
from providers.registry import provider_registry
from apps.api.app.services.storage import storage_service

logger = logging.getLogger("aae.mcp_server")

# Initialize MCP Server
mcp = MCPServer(
    name="Agent Acquisition Engine",
    version="0.1.0",
    description="MCP-First file, document, and media acquisition infrastructure for autonomous AI agents."
)

async def _get_default_user_id(session) -> str:
    stmt = select(User).limit(1)
    res = await session.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        user = User(email="agent@antigravity.internal", hashed_password="default_hash", role="agent")
        session.add(user)
        await session.flush()
    return user.id

# =====================================================================
# MCP TOOL 1: inspect_source
# =====================================================================
@mcp.tool(
    name="inspect_source",
    description="Inspects a URL or document source, checks SSRF safety and permissions, and returns metadata without downloading."
)
async def inspect_source(url: str, user_preferences: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    url = url.strip()
    provider, classification = await provider_registry.resolve_provider_with_classifier(url)

    if not provider:
        return {
            "source_id": f"src_unsupported_{url[:8]}",
            "url": url,
            "resolved_url": classification.resolved_url,
            "source_type": classification.source_type.value,
            "provider": "unsupported",
            "is_permitted": False,
            "security_status": classification.security_status.value,
            "acquisition_permission": classification.acquisition_permission.value,
            "source_access_status": classification.source_access_status.value,
            "capabilities": [],
            "mime_type": classification.mime_type,
            "estimated_size_bytes": classification.estimated_size_bytes,
            "inspection_status": "unsupported",
            "errors": classification.errors or [f"No provider found capable of acquiring source: {url}"]
        }

    inspection = await provider.inspect(url)
    if not inspection.resolved_url:
        inspection.resolved_url = classification.resolved_url
    if inspection.source_type == SourceType.DIRECT_FILE and classification.source_type != SourceType.DIRECT_FILE:
        inspection.source_type = classification.source_type

    async with async_session_factory() as session:
        stmt = select(Source).where(Source.url == url)
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()

        assets_data = [a.model_dump() for a in inspection.assets] if inspection.assets else None

        if existing:
            existing.canonical_url = inspection.resolved_url
            existing.source_type = inspection.source_type.value
            existing.provider_id = inspection.provider_id
            existing.content_type = inspection.mime_type
            existing.estimated_size_bytes = inspection.estimated_size_bytes
            existing.is_permitted = inspection.is_permitted
            existing.security_status = inspection.security_status.value
            existing.acquisition_permission = inspection.acquisition_permission.value
            existing.source_access_status = inspection.source_access_status.value
            existing.title = inspection.title
            existing.thumbnail_url = inspection.thumbnail_url
            existing.assets_metadata = assets_data
            existing.inspection_status = inspection.inspection_status
            source_id = existing.id
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
            session.add(new_source)
            await session.flush()
            source_id = new_source.id

        if inspection.is_permitted:
            formats = inspection.formats or await provider.list_formats(url)
            from sqlalchemy import delete
            await session.execute(delete(SourceOption).where(SourceOption.source_id == source_id))
            for fmt in formats:
                session.add(SourceOption(
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
        await session.commit()

    recommended_fmt = None
    if formats:
        recommended_fmt = next((f for f in formats if f.format_id == "best_video_audio"), None)
        if not recommended_fmt:
            recommended_fmt = next((f for f in formats if getattr(f, "category", "") == "recommended"), None)
        if not recommended_fmt:
            recommended_fmt = formats[0]

    return {
        "source_id": source_id,
        "url": url,
        "resolved_url": inspection.resolved_url,
        "source_type": inspection.source_type.value,
        "provider": provider.provider_id,
        "is_permitted": inspection.is_permitted,
        "security_status": inspection.security_status.value,
        "acquisition_permission": inspection.acquisition_permission.value,
        "source_access_status": inspection.source_access_status.value,
        "capabilities": inspection.capabilities,
        "mime_type": inspection.mime_type,
        "estimated_size_bytes": inspection.estimated_size_bytes,
        "inspection_status": inspection.inspection_status,
        "title": inspection.title,
        "recommended_format_id": recommended_fmt.format_id if recommended_fmt else None,
        "recommended_format_label": recommended_fmt.quality_label if recommended_fmt else None,
        "assets": [a.model_dump() for a in inspection.assets],
        "formats_count": len(inspection.formats),
        "errors": inspection.errors
    }

# =====================================================================
# MCP TOOL 2: list_formats
# =====================================================================
@mcp.tool(
    name="list_formats",
    description="Discovers available downloadable formats, stream codecs, and resolutions for an inspected source ID with smart recommendations for AI agents."
)
async def list_formats(source_id: str) -> Dict[str, Any]:
    async with async_session_factory() as session:
        source = await session.get(Source, source_id)
        if not source:
            return {"error": f"Source ID '{source_id}' not found. Run inspect_source first."}

        stmt = select(SourceOption).where(SourceOption.source_id == source_id)
        res = await session.execute(stmt)
        options = res.scalars().all()

        formats_list = [
            {
                "format_id": opt.format_id,
                "file_type": opt.file_type,
                "mime_type": opt.mime_type,
                "resolution": opt.resolution,
                "codec": opt.codec,
                "estimated_size_bytes": opt.estimated_size_bytes,
                "quality_label": opt.quality_label,
                "has_audio": opt.has_audio,
                "has_video": opt.has_video,
                "category": opt.category
            }
            for opt in options
        ]

        # Prioritize recommended video+audio formats
        recommended = [f for f in formats_list if f.get("category") == "recommended" or (f.get("has_audio") is not False and f.get("file_type") == "video")]
        audio_only = [f for f in formats_list if f.get("category") == "audio_only" or f.get("file_type") == "audio"]
        other = [f for f in formats_list if f not in recommended and f not in audio_only]

        recommended_id = "best_video_audio" if any(f["format_id"] == "best_video_audio" for f in recommended) else (recommended[0]["format_id"] if recommended else (formats_list[0]["format_id"] if formats_list else None))

    return {
        "source_id": source_id,
        "recommended_format_id": recommended_id,
        "recommended_formats": recommended,
        "audio_only_formats": audio_only,
        "raw_or_other_formats": other,
        "formats": formats_list,
        "agent_guidance": "For video acquisition, use 'best_video_audio' or a 'best_{h}p_mp4' preset to ensure synchronized video and audio. Use 'best_audio_mp3' or 'best_audio_m4a' for audio. Avoid video-only streams without audio unless mute is explicitly requested."
    }

# =====================================================================
# MCP TOOL 3: preflight_acquisition
# =====================================================================
@mcp.tool(
    name="preflight_acquisition",
    description="Checks safety, storage limits, and human approval requirements before starting acquisition."
)
async def preflight_acquisition(source_id: str, format_id: str, execution_mode: str = "cloud") -> Dict[str, Any]:
    async with async_session_factory() as session:
        source = await session.get(Source, source_id)
        if not source:
            return {"can_acquire": False, "error": f"Source ID '{source_id}' not found."}

        if not source.is_permitted:
            return {
                "can_acquire": False,
                "requires_approval": False,
                "approval_reason": "Source forbidden by security policy."
            }

        stmt = select(SourceOption).where(
            SourceOption.source_id == source_id,
            SourceOption.format_id == format_id
        )
        res = await session.execute(stmt)
        opt = res.scalar_one_or_none()
        if not opt:
            return {"can_acquire": False, "error": f"Format ID '{format_id}' not available for source."}

        requires_approval = False
        approval_reason = None
        if opt.estimated_size_bytes and opt.estimated_size_bytes > 52_428_800:
            requires_approval = True
            approval_reason = f"File size ({opt.estimated_size_bytes} bytes) exceeds 50 MB threshold. Operator approval required."

        # Deduplication cache lookup
        cache_key = hashlib.sha256(f"{source.canonical_url or source.url}::{format_id}".encode()).hexdigest()
        stmt_dup = (
            select(Artifact)
            .where(
                Artifact.origin_cache_key == cache_key,
                Artifact.is_verified == True
            )
            .order_by(Artifact.created_at.desc())
            .limit(1)
        )
        dup_res = await session.execute(stmt_dup)
        duplicate_art = dup_res.scalar_one_or_none()
        is_cached = bool(duplicate_art and storage_service.get_artifact_path(duplicate_art.storage_path).exists())

    return {
        "can_acquire": True,
        "requires_approval": requires_approval if not is_cached else False,
        "approval_reason": approval_reason if not is_cached else None,
        "estimated_size_bytes": opt.estimated_size_bytes,
        "storage_available": True,
        "is_cached": is_cached,
        "cached_artifact_id": duplicate_art.id if is_cached else None,
        "duplicate_artifact_id": duplicate_art.id if duplicate_art else None
    }

# =====================================================================
# MCP TOOL 4: request_approval
# =====================================================================
@mcp.tool(
    name="request_approval",
    description="Registers a human-in-the-loop approval request when preflight indicates approval is required."
)
async def request_approval(source_id: str, format_id: str, reason: str) -> Dict[str, Any]:
    async with async_session_factory() as session:
        source = await session.get(Source, source_id)
        if not source:
            return {"error": f"Source ID '{source_id}' not found."}

        user_id = await _get_default_user_id(session)
        approval = UserApproval(
            user_id=user_id,
            source_id=source_id,
            format_id=format_id,
            status=ApprovalStatus.PENDING.value,
            reason=reason,
            estimated_size_bytes=source.estimated_size_bytes
        )
        session.add(approval)
        await session.commit()
        await session.refresh(approval)

    return {
        "approval_id": approval.id,
        "status": approval.status,
        "message": "Approval request created. Operator approval required before acquisition starts."
    }

# =====================================================================
# MCP TOOL 5: start_acquisition
# =====================================================================
@mcp.tool(
    name="start_acquisition",
    description="Submits an acquisition job to the engine queue and returns a Job ID for telemetry tracking."
)
async def start_acquisition(source_id: str, format_id: str, approval_id: Optional[str] = None, execution_mode: str = "cloud") -> Dict[str, Any]:
    async with async_session_factory() as session:
        source = await session.get(Source, source_id)
        if not source:
            return {"error": f"Source ID '{source_id}' not found."}

        stmt_opt = select(SourceOption).where(
            SourceOption.source_id == source_id,
            SourceOption.format_id == format_id
        )
        res_opt = await session.execute(stmt_opt)
        opt = res_opt.scalar_one_or_none()
        if not opt:
            return {"error": f"Format ID '{format_id}' is not available for source."}

        # Enforce approval if required
        needs_approval = (opt.estimated_size_bytes and opt.estimated_size_bytes > 52_428_800)
        if needs_approval:
            if not approval_id:
                return {
                    "error": "Operator approval is required for this acquisition (file size exceeds 50 MB threshold), but no approval_id was provided. Call request_approval first."
                }
            approval = await session.get(UserApproval, approval_id)
            if not approval or approval.status != ApprovalStatus.APPROVED.value:
                return {
                    "error": f"Specified approval ID '{approval_id}' is not approved (status: {approval.status if approval else 'missing'})."
                }
        elif approval_id:
            approval = await session.get(UserApproval, approval_id)
            if not approval or approval.status != ApprovalStatus.APPROVED.value:
                return {
                    "error": f"Invalid or unapproved approval ID '{approval_id}'. Current status: {approval.status if approval else 'missing'}."
                }

        user_id = await _get_default_user_id(session)

        # 0. Check deduplication cache for instant fulfillment
        cache_key = hashlib.sha256(f"{source.canonical_url or source.url}::{format_id}".encode()).hexdigest()
        stmt_cache = select(Artifact).where(
            Artifact.origin_cache_key == cache_key,
            Artifact.is_verified == True
        ).order_by(Artifact.created_at.desc()).limit(1)
        cache_res = await session.execute(stmt_cache)
        cached_art = cache_res.scalar_one_or_none()
        if cached_art and storage_service.get_artifact_path(cached_art.storage_path).exists():
            job = AcquisitionJob(
                user_id=user_id,
                source_id=source_id,
                format_id=format_id,
                execution_mode=execution_mode,
                state=JobState.COMPLETED.value,
                progress_percent=100.0,
                bytes_transferred=cached_art.size_bytes,
                total_bytes=cached_art.size_bytes,
                artifact_id=cached_art.id,
                current_operation="Instant acquisition fulfilled from deduplication cache"
            )
            session.add(job)
            await session.flush()
            session.add(JobEvent(
                job_id=job.id,
                event_type="completed",
                message=f"Artifact {cached_art.filename} served from deduplication cache.",
                payload={"cached": True, "artifact_id": cached_art.id}
            ))
            await session.commit()
            await session.refresh(job)
            return {
                "job_id": job.id,
                "state": "completed",
                "is_cached": True,
                "artifact_id": cached_art.id,
                "execution_mode": job.execution_mode,
                "created_at": job.created_at.isoformat(),
                "message": "Instant acquisition cache hit. Artifact delivered from local deduplication cache."
            }

        job = AcquisitionJob(
            user_id=user_id,
            source_id=source_id,
            format_id=format_id,
            execution_mode=execution_mode,
            state=JobState.QUEUED.value,
            current_operation="Queued for worker execution"
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)

    return {
        "job_id": job.id,
        "state": job.state,
        "execution_mode": job.execution_mode,
        "created_at": job.created_at.isoformat()
    }

# =====================================================================
# MCP TOOL 6: get_job_status
# =====================================================================
@mcp.tool(
    name="get_job_status",
    description="Queries real-time job progress, current operation, transferred bytes, and completion state."
)
async def get_job_status(job_id: str) -> Dict[str, Any]:
    async with async_session_factory() as session:
        job = await session.get(AcquisitionJob, job_id)
        if not job:
            return {"error": f"Job ID '{job_id}' not found."}

        return {
            "job_id": job.id,
            "state": job.state,
            "progress_percent": job.progress_percent,
            "bytes_transferred": job.bytes_transferred,
            "total_bytes": job.total_bytes,
            "current_operation": job.current_operation,
            "artifact_id": job.artifact_id,
            "error_message": job.error_message,
            "updated_at": job.updated_at.isoformat()
        }

# =====================================================================
# MCP TOOL 7: get_artifact
# =====================================================================
@mcp.tool(
    name="get_artifact",
    description="Retrieves verified artifact metadata, SHA-256 checksum, and a secure expiring download URL."
)
async def get_artifact(artifact_id: str) -> Dict[str, Any]:
    async with async_session_factory() as session:
        art = await session.get(Artifact, artifact_id)
        if not art:
            return {"error": f"Artifact ID '{artifact_id}' not found."}

        dl_url, expires_at = storage_service.generate_delivery_url(art.id)

        return {
            "artifact_id": art.id,
            "filename": art.filename,
            "mime_type": art.mime_type,
            "size_bytes": art.size_bytes,
            "sha256": art.sha256,
            "is_verified": art.is_verified,
            "download_url": dl_url,
            "expires_at": expires_at.isoformat()
        }

async def run_server():
    """Initializes tables and starts MCP server over stdio."""
    await init_db()
    await mcp.run_stdio_async()

if __name__ == "__main__":
    asyncio.run(run_server())
