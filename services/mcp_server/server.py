import asyncio
import logging
import hashlib
import os
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from mcp.server.mcpserver import MCPServer, Context
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.auth.middleware.auth_context import get_access_token
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
    User,
    AgentConnection
)
from apps.api.app.security.tokens import hash_api_key
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

class _DatabaseTokenVerifier:
    async def verify_token(self, token: str) -> Optional[AccessToken]:
        async with async_session_factory() as session:
            if token.startswith("aae_live_"):
                stmt = select(AgentConnection).where(
                    AgentConnection.api_key_hash == hash_api_key(token)
                )
                result = await session.execute(stmt)
                connection = result.scalar_one_or_none()
                if not connection:
                    return None
                user = await session.get(User, connection.user_id)
                if not user:
                    return None
                connection.last_active_at = datetime.now(timezone.utc)
                await session.commit()
                return AccessToken(
                    token=token,
                    client_id=connection.id,
                    subject=user.id,
                    scopes=[
                        permission
                        for permission in (connection.permissions or [])
                        if permission in {"read", "acquire"}
                    ],
                    claims={"credential_type": "agent", "role": user.role}
                )

            if token.startswith("aae_usr_"):
                stmt = select(User).where(User.portal_token == token)
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()
                if not user:
                    return None
                return AccessToken(
                    token=token,
                    client_id=f"user:{user.id}",
                    subject=user.id,
                    scopes=["read", "acquire", "approve"],
                    claims={"credential_type": "portal", "role": user.role}
                )

        return None

def _is_admin_credential(
    user: User,
    api_key: Optional[str] = None,
    token: Optional[str] = None
) -> bool:
    access_token = get_access_token()
    if access_token:
        credential_type = (access_token.claims or {}).get("credential_type")
        return user.role == "admin" and credential_type == "portal"
    if api_key or (not token and os.environ.get("MCP_AUTH_TOKEN", "").startswith("aae_live_")):
        return False
    return user.role == "admin"

# Initialize MCP Server
mcp = MCPServer(
    name="Agent Acquisition Engine",
    version="0.1.0",
    description="MCP-First file, document, and media acquisition infrastructure for autonomous AI agents.",
    auth=AuthSettings(
        issuer_url=settings.API_BASE_URL,
        resource_server_url=None,
        required_scopes=["read"]
    ),
    token_verifier=_DatabaseTokenVerifier()
)

async def _get_default_user_id(session) -> str:
    import secrets
    stmt = select(User).limit(1)
    res = await session.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        user = User(
            email="agent@engine.io",
            hashed_password="default_hash",
            role="agent",
            portal_token=f"aae_usr_{secrets.token_hex(20)}"
        )
        session.add(user)
        await session.flush()
    elif not user.portal_token:
        user.portal_token = f"aae_usr_{secrets.token_hex(20)}"
        await session.flush()
    return user.id

async def _resolve_user_from_credentials(
    session,
    api_key: Optional[str] = None,
    token: Optional[str] = None,
    required_permission: str = "read"
) -> tuple[Optional[User], Optional[str]]:
    """
    Resolves and authenticates the user for an MCP tool request.
    Supports MCP bearer auth, local stdio credentials, and development-only fallback.
    """
    access_token = get_access_token()
    if access_token:
        supplied = api_key or token
        if supplied:
            supplied = supplied.removeprefix("Bearer ").strip()
            if supplied != access_token.token:
                return None, "Tool credentials do not match the authenticated MCP connection."
        if required_permission not in access_token.scopes:
            return None, f"The authenticated credential does not have the '{required_permission}' permission."
        if not access_token.subject:
            return None, "Authenticated MCP credential has no user identity."
        user = await session.get(User, access_token.subject)
        if not user:
            return None, "User account associated with MCP credential not found."
        return user, None

    if not api_key and not token:
        token = os.environ.get("MCP_AUTH_TOKEN")
        if token and token.startswith("aae_live_"):
            api_key, token = token, None

    if api_key:
        api_key = api_key.strip()
        if api_key.startswith("Bearer "):
            api_key = api_key[7:].strip()
        if not api_key.startswith("aae_live_"):
            return None, "Invalid agent API key format. Expected 'aae_live_...' prefix."
        hashed = hash_api_key(api_key)
        stmt = select(AgentConnection).where(AgentConnection.api_key_hash == hashed)
        res = await session.execute(stmt)
        conn = res.scalar_one_or_none()
        if not conn:
            return None, "Invalid or revoked agent API key."
        user = await session.get(User, conn.user_id)
        if not user:
            return None, "User account associated with API key not found."
        if required_permission not in (conn.permissions or []):
            return None, f"The agent API key does not have the '{required_permission}' permission."
        return user, None

    if token:
        token = token.strip()
        if token.startswith("Bearer "):
            token = token[7:].strip()
        if not token.startswith("aae_usr_"):
            return None, "Invalid user token format. Expected 'aae_usr_...' prefix."
        stmt = select(User).where(User.portal_token == token)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        if not user:
            return None, "Invalid or expired personal dashboard token."
        if required_permission not in {"read", "acquire", "approve"}:
            return None, f"The user portal credential does not have the '{required_permission}' permission."
        return user, None

    if settings.ENVIRONMENT.lower() in {"development", "dev", "test"}:
        user_id = await _get_default_user_id(session)
        user = await session.get(User, user_id)
        return user, None
    return None, "Authentication is required. Configure a bearer token for the MCP server."

def make_error_envelope(
    code: str,
    message: str,
    retryable: bool = False,
    remediation: str = "",
    details: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    res: Dict[str, Any] = {
        "ok": False,
        "success": False,
        "error": message,
        "error_code": code,
        "error_envelope": {
            "code": code,
            "message": message,
            "retryable": retryable,
            "remediation": remediation,
            "details": details or {}
        },
        "meta": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "engine_version": "0.2.0"
        }
    }
    if extra:
        res.update(extra)
    return res

def make_success_envelope(data: Dict[str, Any]) -> Dict[str, Any]:
    res = dict(data)
    res["ok"] = True
    res["success"] = True
    res["data"] = dict(data)
    res["error"] = None
    res["meta"] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "engine_version": "0.2.0"
    }
    return res

# =====================================================================
# MCP TOOL 1: inspect_source
# =====================================================================
async def inspect_source(
    url: str,
    user_preferences: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    token: Optional[str] = None
) -> Dict[str, Any]:
    url = url.strip()
    async with async_session_factory() as session:
        _, auth_err = await _resolve_user_from_credentials(
            session, api_key=api_key, token=token, required_permission="read"
        )
        if auth_err:
            return make_error_envelope(
                code="AUTH_REQUIRED",
                message=auth_err,
                extra={
                    "source_id": f"src_auth_err_{url[:8]}",
                    "url": url,
                    "is_permitted": False,
                    "security_status": "blocked",
                    "inspection_status": "failed",
                    "errors": [auth_err]
                }
            )

    provider, classification = await provider_registry.resolve_provider_with_classifier(url)

    if not provider:
        return make_error_envelope(
            code="UNSUPPORTED_SOURCE",
            message=classification.errors[0] if classification.errors else f"No provider found capable of acquiring source: {url}",
            extra={
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
        )

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

        formats = inspection.formats or []
        if not formats and inspection.is_permitted:
            formats = await provider.list_formats(url)
        if formats:
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
                    category=fmt.category,
                    status=getattr(fmt, "status", "ready") or "ready",
                    status_reason=getattr(fmt, "status_reason", None)
                ))
        await session.commit()

    recommended_fmt = None
    if formats:
        recommended_fmt = next((f for f in formats if f.format_id == "best_video_audio"), None)
        if not recommended_fmt:
            recommended_fmt = next((f for f in formats if getattr(f, "category", "") == "recommended"), None)
        if not recommended_fmt:
            recommended_fmt = formats[0]

    calc_size = inspection.estimated_size_bytes
    if calc_size is None and recommended_fmt:
        calc_size = recommended_fmt.estimated_size_bytes

    if not inspection.is_permitted:
        requires_approval = False
        approval_reason = None
    elif calc_size is None:
        requires_approval = True
        approval_reason = "File size is unknown. Operator approval required before acquisition."
    elif calc_size > 52_428_800:
        requires_approval = True
        approval_reason = f"Estimated file size ({calc_size} bytes) exceeds 50 MB threshold. Operator approval required."
    else:
        requires_approval = False
        approval_reason = None

    return make_success_envelope({
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
        "requires_approval": requires_approval,
        "approval_reason": approval_reason,
        "inspection_status": inspection.inspection_status,
        "title": inspection.title,
        "thumbnail_url": inspection.thumbnail_url,
        "duration_seconds": inspection.assets[0].duration_seconds if inspection.assets else None,
        "recommended_format_id": recommended_fmt.format_id if recommended_fmt else None,
        "recommended_format_label": recommended_fmt.quality_label if recommended_fmt else None,
        "assets": [a.model_dump() for a in inspection.assets],
        "formats_count": len(formats),
        "errors": inspection.errors
    })

# =====================================================================
# MCP TOOL 2: list_formats
# =====================================================================
async def list_formats(
    source_id: str,
    api_key: Optional[str] = None,
    token: Optional[str] = None
) -> Dict[str, Any]:
    async with async_session_factory() as session:
        _, auth_err = await _resolve_user_from_credentials(
            session, api_key=api_key, token=token, required_permission="read"
        )
        if auth_err:
            return make_error_envelope(code="AUTH_REQUIRED", message=auth_err)

        source = await session.get(Source, source_id)
        if not source:
            return make_error_envelope(
                code="NOT_FOUND",
                message=f"Source ID '{source_id}' not found. Run inspect_source first.",
                remediation="Call inspect_source(url) first to register the source."
            )

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
                "category": opt.category,
                "status": getattr(opt, "status", "ready") or "ready",
                "status_reason": getattr(opt, "status_reason", None)
            }
            for opt in options
        ]

        # Prioritize recommended video+audio formats
        recommended = [f for f in formats_list if f.get("category") == "recommended" or (f.get("has_audio") is not False and f.get("file_type") == "video")]
        audio_only = [f for f in formats_list if f.get("category") == "audio_only" or f.get("file_type") == "audio"]
        other = [f for f in formats_list if f not in recommended and f not in audio_only]

        recommended_id = "best_video_audio" if any(f["format_id"] == "best_video_audio" for f in recommended) else (recommended[0]["format_id"] if recommended else (formats_list[0]["format_id"] if formats_list else None))

    return make_success_envelope({
        "source_id": source_id,
        "recommended_format_id": recommended_id,
        "recommended_formats": recommended,
        "audio_only_formats": audio_only,
        "raw_or_other_formats": other,
        "formats": formats_list,
        "agent_guidance": "For video acquisition, use 'best_video_audio' or a 'best_{h}p_mp4' preset to ensure synchronized video and audio. Use 'best_audio_mp3' or 'best_audio_m4a' for audio. Avoid video-only streams without audio unless mute is explicitly requested."
    })

# =====================================================================
# MCP TOOL 3: preflight_acquisition
# =====================================================================
async def preflight_acquisition(
    source_id: str,
    format_id: str,
    execution_mode: str = "cloud",
    api_key: Optional[str] = None,
    token: Optional[str] = None
) -> Dict[str, Any]:
    async with async_session_factory() as session:
        user, auth_err = await _resolve_user_from_credentials(
            session, api_key=api_key, token=token, required_permission="read"
        )
        if auth_err:
            return make_error_envelope(code="AUTH_REQUIRED", message=auth_err, extra={"can_acquire": False})

        source = await session.get(Source, source_id)
        if not source:
            return make_error_envelope(code="NOT_FOUND", message=f"Source ID '{source_id}' not found.", extra={"can_acquire": False})

        if not source.is_permitted:
            return make_error_envelope(
                code="FORBIDDEN_POLICY",
                message="Source forbidden by security policy.",
                extra={
                    "can_acquire": False,
                    "requires_approval": False,
                    "approval_reason": "Source forbidden by security policy."
                }
            )

        stmt = select(SourceOption).where(
            SourceOption.source_id == source_id,
            SourceOption.format_id == format_id
        )
        res = await session.execute(stmt)
        opt = res.scalar_one_or_none()
        if not opt:
            return make_error_envelope(
                code="FORMAT_UNAVAILABLE",
                message=f"Format ID '{format_id}' not available for source.",
                remediation="Call list_formats(source_id) to select an available format.",
                extra={"can_acquire": False}
            )

        if opt.estimated_size_bytes and opt.estimated_size_bytes > settings.MAX_FILE_SIZE_BYTES:
            return make_error_envelope(
                code="QUOTA_EXCEEDED",
                message=f"Acquisition rejected: File size ({opt.estimated_size_bytes} bytes) exceeds maximum engine quota limit ({settings.MAX_FILE_SIZE_BYTES} bytes).",
                remediation="Select a smaller format or contact operator.",
                extra={"can_acquire": False}
            )

        requires_approval = opt.estimated_size_bytes is None or opt.estimated_size_bytes > 52_428_800
        approval_reason = None
        if opt.estimated_size_bytes is None:
            approval_reason = "File size is unknown. Operator approval is required before acquisition."
        elif requires_approval:
            requires_approval = True
            approval_reason = f"File size ({opt.estimated_size_bytes} bytes) exceeds 50 MB threshold. Operator approval required."

        # Deduplication cache lookup
        cache_key = hashlib.sha256(f"{source.canonical_url or source.url}::{format_id}".encode()).hexdigest()
        stmt_dup = (
            select(Artifact)
            .where(
                Artifact.origin_cache_key == cache_key,
                Artifact.user_id == user.id,
                Artifact.is_verified == True
            )
            .order_by(Artifact.created_at.desc())
            .limit(1)
        )
        dup_res = await session.execute(stmt_dup)
        duplicate_art = dup_res.scalar_one_or_none()
        artifact_path = storage_service.get_artifact_path(duplicate_art.storage_path) if duplicate_art else None
        is_cached = artifact_path is not None
        if is_cached:
            requires_approval = False
            approval_reason = None

    return make_success_envelope({
        "can_acquire": True,
        "requires_approval": requires_approval,
        "approval_reason": approval_reason,
        "estimated_size_bytes": opt.estimated_size_bytes,
        "storage_available": True,
        "is_cached": is_cached,
        "cached_artifact_id": duplicate_art.id if is_cached else None,
        "duplicate_artifact_id": duplicate_art.id if duplicate_art else None
    })

# =====================================================================
# MCP TOOL 4: request_approval
# =====================================================================
async def request_approval(
    source_id: str,
    format_id: str,
    reason: str,
    api_key: Optional[str] = None,
    token: Optional[str] = None
) -> Dict[str, Any]:
    async with async_session_factory() as session:
        user, auth_err = await _resolve_user_from_credentials(
            session, api_key=api_key, token=token, required_permission="acquire"
        )
        if auth_err:
            return make_error_envelope(code="AUTH_REQUIRED", message=auth_err)

        source = await session.get(Source, source_id)
        if not source:
            return make_error_envelope(code="NOT_FOUND", message=f"Source ID '{source_id}' not found.")
        if not source.is_permitted:
            return make_error_envelope(code="FORBIDDEN_POLICY", message="Source is forbidden by security policy.")
        option_result = await session.execute(
            select(SourceOption).where(
                SourceOption.source_id == source_id,
                SourceOption.format_id == format_id
            )
        )
        option = option_result.scalar_one_or_none()
        if not option:
            return make_error_envelope(code="FORMAT_UNAVAILABLE", message=f"Format ID '{format_id}' is not available for source.")

        approval = UserApproval(
            user_id=user.id,
            source_id=source_id,
            format_id=format_id,
            status=ApprovalStatus.PENDING.value,
            reason=reason,
            estimated_size_bytes=option.estimated_size_bytes
        )
        session.add(approval)
        await session.commit()
        await session.refresh(approval)

    return make_success_envelope({
        "approval_id": approval.id,
        "status": approval.status,
        "message": "Approval request created. Operator approval required before acquisition starts."
    })

# =====================================================================
# MCP TOOL 5: start_acquisition
# =====================================================================
async def start_acquisition(
    source_id: str,
    format_id: str,
    approval_id: Optional[str] = None,
    execution_mode: str = "cloud",
    delivery_target: Optional[Dict[str, Any]] = None,
    privacy: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    token: Optional[str] = None
) -> Dict[str, Any]:
    async with async_session_factory() as session:
        user, auth_err = await _resolve_user_from_credentials(
            session, api_key=api_key, token=token, required_permission="acquire"
        )
        if auth_err:
            return make_error_envelope(code="AUTH_REQUIRED", message=auth_err)

        source = await session.get(Source, source_id)
        if not source:
            return make_error_envelope(code="NOT_FOUND", message=f"Source ID '{source_id}' not found.")
        if not source.is_permitted:
            return make_error_envelope(code="FORBIDDEN_POLICY", message="Source is forbidden by security policy.")

        stmt_opt = select(SourceOption).where(
            SourceOption.source_id == source_id,
            SourceOption.format_id == format_id
        )
        res_opt = await session.execute(stmt_opt)
        opt = res_opt.scalar_one_or_none()
        if not opt:
            return make_error_envelope(code="FORMAT_UNAVAILABLE", message=f"Format ID '{format_id}' is not available for source.")

        if opt.estimated_size_bytes and opt.estimated_size_bytes > settings.MAX_FILE_SIZE_BYTES:
            return make_error_envelope(
                code="QUOTA_EXCEEDED",
                message=f"Acquisition rejected: File size ({opt.estimated_size_bytes} bytes) exceeds maximum engine quota limit ({settings.MAX_FILE_SIZE_BYTES} bytes)."
            )

        user_id = user.id
        dashboard_base = settings.FRONTEND_URL.rstrip("/") if hasattr(settings, "FRONTEND_URL") and settings.FRONTEND_URL else (
            settings.CORS_ORIGINS[0].rstrip("/") if settings.CORS_ORIGINS else "http://localhost:5173"
        )
        dashboard_url = f"{dashboard_base}/portal"

        cache_key = hashlib.sha256(f"{source.canonical_url or source.url}::{format_id}".encode()).hexdigest()
        stmt_user_cache = select(Artifact).where(
            Artifact.origin_cache_key == cache_key,
            Artifact.user_id == user_id,
            Artifact.is_verified == True
        ).order_by(Artifact.created_at.desc()).limit(1)
        user_cache_res = await session.execute(stmt_user_cache)
        user_cached_art = user_cache_res.scalar_one_or_none()
        user_cached_path = (
            storage_service.get_artifact_path(user_cached_art.storage_path)
            if user_cached_art else None
        )

        needs_approval = (
            not user_cached_path
            and (opt.estimated_size_bytes is None or opt.estimated_size_bytes > 52_428_800)
        )
        approval = None
        if needs_approval:
            if not approval_id:
                return make_error_envelope(
                    code="APPROVAL_REQUIRED",
                    message="Operator approval is required for this acquisition (file size is unknown or exceeds 50 MB), but no approval_id was provided. Call request_approval first.",
                    remediation="Call request_approval(source_id, format_id, reason) first."
                )
            approval = await session.get(UserApproval, approval_id)
            if (
                not approval
                or approval.status != ApprovalStatus.APPROVED.value
                or approval.user_id != user.id
                or approval.source_id != source_id
                or approval.format_id != format_id
            ):
                return make_error_envelope(
                    code="APPROVAL_REQUIRED",
                    message="Specified approval is missing, unapproved, or does not match this user, source, and format.",
                    remediation="Wait for operator approval or verify approval_id."
                )
        elif approval_id:
            approval = await session.get(UserApproval, approval_id)
            if (
                not approval
                or approval.status != ApprovalStatus.APPROVED.value
                or approval.user_id != user.id
                or approval.source_id != source_id
                or approval.format_id != format_id
            ):
                return make_error_envelope(
                    code="APPROVAL_REQUIRED",
                    message="Specified approval is missing, unapproved, or does not match this user, source, and format.",
                    remediation="Wait for operator approval or verify approval_id."
                )

        target_cfg = delivery_target or ({"type": "ephemeral"} if privacy and privacy.get("retention") == "none" else {"type": "local"})
        privacy_cfg = privacy or {
            "egress": "pooled",
            "retention": "none" if target_cfg.get("type") == "ephemeral" else "persistent",
            "log_level": "metadata_only"
        }

        stmt_cache = select(Artifact).where(
            Artifact.origin_cache_key == cache_key,
            Artifact.is_verified == True
        ).order_by(Artifact.created_at.desc()).limit(1)
        cache_res = await session.execute(stmt_cache)
        cached_art = cache_res.scalar_one_or_none()
        cached_path = storage_service.get_artifact_path(cached_art.storage_path) if cached_art else None

        # Invalidate false audio cache if a video format was requested
        is_bad_video_cache = False
        if cached_art and opt.file_type == "video":
            if cached_art.mime_type.startswith("audio/") or cached_art.filename.lower().endswith((".m4a", ".mp3", ".aac")):
                is_bad_video_cache = True
                cached_art.is_verified = False
                await session.commit()
                cached_art = None
                cached_path = None

        if cached_art and cached_path:
            if cached_art.user_id != user_id:
                cached_art = Artifact(
                    user_id=user_id,
                    filename=cached_art.filename,
                    mime_type=cached_art.mime_type,
                    size_bytes=cached_art.size_bytes,
                    sha256=cached_art.sha256,
                    storage_path=cached_art.storage_path,
                    is_verified=True,
                    origin_cache_key=cache_key
                )
                session.add(cached_art)
                await session.flush()
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
                payload={"cached": True, "artifact_id": cached_art.id, "delivery_target": target_cfg, "privacy": privacy_cfg}
            ))
            await session.commit()
            await session.refresh(job)
            return make_success_envelope({
                "job_id": job.id,
                "state": "completed",
                "is_cached": True,
                "artifact_id": cached_art.id,
                "execution_mode": job.execution_mode,
                "delivery_target": target_cfg,
                "privacy": privacy_cfg,
                "user_dashboard_url": dashboard_url,
                "created_at": job.created_at.isoformat(),
                "message": "Instant acquisition cache hit. Artifact delivered from local deduplication cache."
            })

        job = AcquisitionJob(
            user_id=user_id,
            source_id=source_id,
            format_id=format_id,
            execution_mode=execution_mode,
            state=JobState.QUEUED.value,
            current_operation="Queued for worker execution"
        )
        session.add(job)
        await session.flush()
        session.add(JobEvent(
            job_id=job.id,
            event_type="queued",
            message="Job queued with target policy.",
            payload={"delivery_target": target_cfg, "privacy": privacy_cfg}
        ))
        await session.commit()
        await session.refresh(job)

    return make_success_envelope({
        "job_id": job.id,
        "state": job.state,
        "execution_mode": job.execution_mode,
        "delivery_target": target_cfg,
        "privacy": privacy_cfg,
        "user_dashboard_url": dashboard_url,
        "created_at": job.created_at.isoformat()
    })

# =====================================================================
# MCP TOOL 6: get_job_status
# =====================================================================
async def get_job_status(
    job_id: str,
    api_key: Optional[str] = None,
    token: Optional[str] = None
) -> Dict[str, Any]:
    async with async_session_factory() as session:
        user, auth_err = await _resolve_user_from_credentials(
            session, api_key=api_key, token=token, required_permission="read"
        )
        if auth_err:
            return make_error_envelope(code="AUTH_REQUIRED", message=auth_err)

        job = await session.get(AcquisitionJob, job_id)
        if not job or (not _is_admin_credential(user, api_key, token) and job.user_id != user.id):
            return make_error_envelope(code="NOT_FOUND", message=f"Job ID '{job_id}' not found.")

        return make_success_envelope({
            "job_id": job.id,
            "state": job.state,
            "progress_percent": job.progress_percent,
            "bytes_transferred": job.bytes_transferred,
            "total_bytes": job.total_bytes,
            "current_operation": job.current_operation,
            "artifact_id": job.artifact_id,
            "error_message": job.error_message,
            "updated_at": job.updated_at.isoformat()
        })

# =====================================================================
# MCP TOOL 7: get_artifact
# =====================================================================
async def get_artifact(
    artifact_id: str,
    api_key: Optional[str] = None,
    token: Optional[str] = None
) -> Dict[str, Any]:
    async with async_session_factory() as session:
        user, auth_err = await _resolve_user_from_credentials(
            session, api_key=api_key, token=token, required_permission="read"
        )
        if auth_err:
            return make_error_envelope(code="AUTH_REQUIRED", message=auth_err)

        art = await session.get(Artifact, artifact_id)
        if not art or not art.is_verified or (not _is_admin_credential(user, api_key, token) and art.user_id != user.id):
            return make_error_envelope(code="NOT_FOUND", message=f"Artifact ID '{artifact_id}' not found.")

        bundle = storage_service.generate_delivery_bundle(art.id)

        preview_meta = art.preview_metadata or {}
        if not preview_meta:
            art_file = storage_service.get_artifact_path(art.storage_path)
            if art_file and art_file.exists():
                preview_meta = storage_service.extract_preview_metadata(art_file, art.mime_type)
                if preview_meta:
                    art.preview_metadata = preview_meta
                    await session.commit()

        return make_success_envelope({
            "artifact_id": art.id,
            "filename": art.filename,
            "mime_type": art.mime_type,
            "size_bytes": art.size_bytes,
            "sha256": art.sha256,
            "is_verified": art.is_verified,
            "download_url": bundle["download_url"],
            "preview_url": bundle["preview_url"],
            "streaming_url": bundle["preview_url"],
            "contact_sheet_url": bundle["contact_sheet_url"] if art.mime_type.startswith("video/") else None,
            "preview_metadata": preview_meta,
            "expires_at": bundle["expires_at"].isoformat()
        })

# =====================================================================
# MCP TOOL 8: get_user_dashboard_link
# =====================================================================
async def get_user_dashboard_link(
    email: Optional[str] = None,
    api_key: Optional[str] = None,
    token: Optional[str] = None
) -> Dict[str, Any]:
    import secrets
    access_token = get_access_token()
    credential_type = (access_token.claims or {}).get("credential_type") if access_token else None
    portal_token = token or os.environ.get("MCP_AUTH_TOKEN", "")
    if access_token and credential_type != "portal":
        return make_error_envelope(code="AUTH_REQUIRED", message="A user portal credential is required to retrieve a dashboard link.")
    if not access_token and not portal_token.startswith("aae_usr_"):
        return make_error_envelope(code="AUTH_REQUIRED", message="A user portal credential is required to retrieve a dashboard link.")
    if api_key:
        return make_error_envelope(code="AUTH_REQUIRED", message="A user portal credential is required to retrieve a dashboard link.")

    async with async_session_factory() as session:
        user, auth_err = await _resolve_user_from_credentials(
            session, api_key=api_key, token=token, required_permission="read"
        )
        if auth_err:
            return make_error_envelope(code="AUTH_REQUIRED", message=auth_err)

        is_admin = _is_admin_credential(user, api_key, token)
        if email and not is_admin and settings.ENVIRONMENT.lower() not in {"development", "dev", "test"}:
            if email.strip().lower() != user.email.lower():
                return make_error_envelope(code="FORBIDDEN_POLICY", message="Only administrators can request a dashboard link for another user.")

        if email and (is_admin or email.strip().lower() == user.email.lower()):
            email_clean = email.strip().lower()
            stmt = select(User).where(User.email == email_clean)
            res = await session.execute(stmt)
            requested_user = res.scalar_one_or_none()
            if not requested_user and is_admin:
                requested_user = User(
                    email=email_clean,
                    hashed_password=f"auto_{secrets.token_hex(16)}",
                    role="user",
                    portal_token=f"aae_usr_{secrets.token_hex(20)}"
                )
                session.add(requested_user)
                await session.commit()
                await session.refresh(requested_user)
            if requested_user:
                user = requested_user
        if not user.portal_token:
            user.portal_token = f"aae_usr_{secrets.token_hex(20)}"
            await session.commit()
            await session.refresh(user)

        dashboard_base = settings.FRONTEND_URL.rstrip("/") if hasattr(settings, "FRONTEND_URL") and settings.FRONTEND_URL else (
            settings.CORS_ORIGINS[0].rstrip("/") if settings.CORS_ORIGINS else "http://localhost:5173"
        )
        dashboard_url = f"{dashboard_base}/portal?token={user.portal_token}"
        how_it_works_url = f"{dashboard_base}/portal?token={user.portal_token}&tab=how-it-works"

        return make_success_envelope({
            "user_id": user.id,
            "email": user.email,
            "portal_token": user.portal_token,
            "dashboard_url": dashboard_url,
            "how_it_works_url": how_it_works_url,
            "message": "Unique personal dashboard link ready. Share this link with the user so they can visit anytime to track downloads, view files, and see how the engine operates."
        })

# =====================================================================
# MCP TOOL 9: describe_capabilities
# =====================================================================
async def describe_capabilities(
    api_key: Optional[str] = None,
    token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Returns engine manifest, active providers, supported media/protocols,
    quota boundaries, rights policies, and system status for autonomous agents.
    """
    async with async_session_factory() as session:
        from sqlalchemy import func
        q_count = await session.execute(
            select(func.count(AcquisitionJob.id)).where(AcquisitionJob.state.in_(["queued", "claimed", "downloading", "processing"]))
        )
        active_jobs = q_count.scalar() or 0

    providers_info = []
    for p in provider_registry.list_providers():
        providers_info.append({
            "provider_id": p.provider_id,
            "display_name": p.display_name,
            "supported_categories": getattr(p, "supported_content_categories", ["media", "document", "archive"]),
        })

    data = {
        "engine_version": "0.2.0",
        "service_name": "Agent Acquisition Engine",
        "status": "operational",
        "active_jobs_in_queue": active_jobs,
        "supported_protocols": ["http", "https", "magnet", "torrent", "embedded", "movie_query"],
        "rights_tiers": [
            "open_access",
            "permissive_media",
            "operator_approval_gated",
            "restricted_commercial_drm"
        ],
        "policy_limits": {
            "max_file_size_bytes": settings.MAX_FILE_SIZE_BYTES,
            "approval_threshold_bytes": 52_428_800,
            "unknown_size_requires_approval": True,
            "default_timeout_seconds": settings.DEFAULT_DOWNLOAD_TIMEOUT_SECONDS,
            "max_retries_per_job": settings.MAX_RETRIES_PER_JOB,
            "ssrf_protection_enabled": settings.ENABLE_SSRF_PROTECTION,
            "supported_storage_modes": ["local", "direct_relay", "s3_compatible"]
        },
        "providers": providers_info,
        "capabilities": [
            "direct_file_streaming",
            "adaptive_video_audio_muxing",
            "ffprobe_stream_contract_validation",
            "sha256_integrity_verification",
            "deduplication_caching",
            "operator_approval_workflows",
            "signed_expiring_delivery_tokens",
            "multi_user_isolation",
            "autonomous_browser_sniffing",
            "movie_intelligence_discovery",
            "intent_discovery_and_search"
        ]
    }
    return make_success_envelope(data)

# =====================================================================
# MCP TOOL 10: search_sources
# =====================================================================
async def search_sources(
    query: str,
    kind: Optional[str] = None,
    max_results: int = 5,
    api_key: Optional[str] = None,
    token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Searches for downloadable content, media streams, open films, archives, or datasets
    matching a natural language query or title. Returns candidate sources ready for format
    inspection or acquisition.
    """
    query = (query or "").strip()
    if not query:
        return make_error_envelope(
            code="INVALID_ARGUMENT",
            message="Search query cannot be empty.",
            remediation="Provide a non-empty search query string."
        )

    candidates = []

    # 1. Movie & Theatrical Intelligence search
    if not kind or kind.lower() in {"movie", "video", "media", "film"}:
        try:
            from providers.movie_intelligence.provider import MovieIntelligenceProvider
            movie_provider = MovieIntelligenceProvider()
            meta = await movie_provider._resolve_movie_metadata(query)
            if meta and meta.get("title"):
                insp = await movie_provider.inspect(query)
                candidates.append({
                    "title": insp.title or meta.get("title"),
                    "url": f"movie:{query}",
                    "candidate_type": "movie_intelligence",
                    "source_type": "MOVIE_INTEL",
                    "provider": "movie_intelligence",
                    "thumbnail_url": insp.thumbnail_url or meta.get("thumbnail_url"),
                    "director": meta.get("director"),
                    "year": meta.get("year"),
                    "cast": meta.get("cast"),
                    "synopsis": meta.get("synopsis"),
                    "ott_platforms": meta.get("ott", []),
                    "formats_count": len(insp.formats or []),
                    "recommended_format_id": "best_video_audio",
                    "relevance_score": 0.95
                })
        except Exception as e:
            logger.debug(f"Movie intelligence search error: {e}")

    # 2. Platform Media search (YouTube / open web via yt-dlp)
    if not kind or kind.lower() in {"video", "audio", "media"}:
        try:
            import yt_dlp
            limit = min(max_results, 5)
            ydl_opts = {
                "quiet": True,
                "extract_flat": True,
                "skip_download": True,
                "no_warnings": True
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
                for entry in info.get("entries", []):
                    entry_url = entry.get("url") or f"https://www.youtube.com/watch?v={entry.get('id')}"
                    entry_title = entry.get("title") or query
                    dur = entry.get("duration")
                    thumbnails = entry.get("thumbnails", [])
                    thumb_url = thumbnails[-1].get("url") if thumbnails else None
                    candidates.append({
                        "title": entry_title,
                        "url": entry_url,
                        "candidate_type": "platform_media",
                        "source_type": "PLATFORM_MEDIA_PAGE",
                        "provider": "permitted_media",
                        "thumbnail_url": thumb_url,
                        "duration_seconds": float(dur) if dur else None,
                        "uploader": entry.get("uploader") or entry.get("channel"),
                        "recommended_format_id": "best_video_audio",
                        "relevance_score": 0.85
                    })
        except Exception as e:
            logger.debug(f"Platform media search error: {e}")

    return make_success_envelope({
        "query": query,
        "kind": kind or "all",
        "results_count": len(candidates),
        "candidates": candidates
    })

# =====================================================================
# MCP TOOL 11: preview_media (Interactive pre-download preview & player)
# =====================================================================
async def preview_media(
    url: str,
    api_key: Optional[str] = None,
    token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Inspects any media URL or social post (YouTube, Instagram, TikTok, Twitter/X,
    Reddit, Vimeo, SoundCloud, PDF, ZIP), generates an inline playable preview,
    extracts metadata, and formats clear user choices for download.
    """
    insp_res = await inspect_source(url, api_key=api_key, token=token)
    if not insp_res.get("success"):
        return insp_res

    data = insp_res.get("data", {})
    source_id = data.get("source_id")
    title = data.get("title") or "Media Resource"
    thumbnail_url = data.get("thumbnail_url")
    duration_seconds = data.get("duration_seconds")
    provider = data.get("provider")

    # Formulate proper direct video playing / web player preview link
    video_playing_url = url
    if "youtube.com" in url or "youtu.be" in url:
        m_yt = re.search(r'(?:v=|\/|youtu\.be\/)([a-zA-Z0-9_-]{11})', url)
        if m_yt:
            video_playing_url = f"https://www.youtube.com/watch?v={m_yt.group(1)}"
    elif "vimeo.com" in url:
        m_vim = re.search(r'vimeo\.com\/(\d+)', url)
        if m_vim:
            video_playing_url = f"https://vimeo.com/{m_vim.group(1)}"

    fmt_res = await list_formats(source_id, api_key=api_key, token=token)
    formats = fmt_res.get("data", {}).get("formats", [])

    has_video = any(f.get("file_type") == "video" or f.get("has_video") for f in formats)
    has_audio = any(f.get("file_type") == "audio" or f.get("has_audio") for f in formats)

    def _format_size(sz_bytes: Optional[int]) -> str:
        if sz_bytes and sz_bytes > 0:
            if sz_bytes >= 1_048_576:
                return f"~{sz_bytes / 1_048_576:.1f} MB"
            return f"{sz_bytes // 1024} KB"
        return "Unknown (Approval Required)"

    options = []
    # If all formats in inspection are marked unavailable (e.g. Cobalt is down, or anti-bot challenge)
    all_unavailable = bool(formats and all(f.get("status") == "unavailable" for f in formats))

    if all_unavailable:
        for f in formats:
            options.append({
                "action": "unavailable",
                "format_type": f.get("file_type") or "media",
                "format_id": f.get("format_id"),
                "resolution": f.get("resolution") or "-",
                "codec": f.get("codec") or "-",
                "estimated_size": _format_size(f.get("estimated_size_bytes")),
                "label": f.get("quality_label") or "Media Stream",
                "description": f"Unavailable: {f.get('status_reason') or 'Service is offline or media stream not exposed.'}",
                "status": "unavailable",
                "status_reason": f.get("status_reason"),
                "recommended": False
            })
    else:
        comp_fmt = next((f for f in formats if f.get("format_id") in ["best_compatible_mp4", "best_compatible"]), None)
        if comp_fmt or has_video:
            target_f = comp_fmt or next((f for f in formats if f.get("file_type") == "video"), None)
            sz_b = target_f.get("estimated_size_bytes") if target_f else None
            res_str = target_f.get("resolution") or "1080p"
            c_codec = target_f.get("codec") or "H.264 / AAC"
            options.append({
                "action": "download_compatible_video",
                "format_type": "video",
                "format_id": target_f.get("format_id") if target_f else "best_compatible_mp4",
                "resolution": res_str,
                "codec": c_codec,
                "estimated_size": _format_size(sz_b),
                "label": f"🎥 Universal Compatible Video ({res_str} {c_codec})",
                "description": "Recommended for universal playback on QuickTime, iPhone, Safari, TVs, and web browsers.",
                "status": target_f.get("status", "ready") if target_f else "ready",
                "status_reason": target_f.get("status_reason") if target_f else None,
                "recommended": True
            })

        master_fmt = next((f for f in formats if f.get("format_id") == "best_video_audio"), None)
        if master_fmt and (not comp_fmt or master_fmt.get("resolution") != comp_fmt.get("resolution") or master_fmt.get("codec") != comp_fmt.get("codec")):
            sz_b = master_fmt.get("estimated_size_bytes")
            res_str = master_fmt.get("resolution") or "Native"
            options.append({
                "action": "download_master_video",
                "format_type": "video",
                "format_id": master_fmt.get("format_id"),
                "resolution": res_str,
                "codec": master_fmt.get("codec") or "Native",
                "estimated_size": _format_size(sz_b),
                "label": f"🌟 Native Master Video ({res_str} {master_fmt.get('codec') or ''})",
                "description": "Highest original fidelity direct from creator master upload.",
                "status": master_fmt.get("status", "ready"),
                "status_reason": master_fmt.get("status_reason"),
                "recommended": False
            })

        compact_fmt = next((f for f in formats if f.get("format_id") in ["best_720p_mp4", "best_804p_mp4", "best_360p_mp4", "best_358p_mp4"]), None)
        if compact_fmt and (not comp_fmt or compact_fmt.get("format_id") != comp_fmt.get("format_id")):
            sz_b = compact_fmt.get("estimated_size_bytes")
            options.append({
                "action": "download_compact_video",
                "format_type": "video",
                "format_id": compact_fmt.get("format_id"),
                "resolution": compact_fmt.get("resolution") or "Standard",
                "codec": compact_fmt.get("codec") or "H.264",
                "estimated_size": _format_size(sz_b),
                "label": f"📱 Balanced / Mobile Video ({compact_fmt.get('resolution')} {compact_fmt.get('codec') or ''})",
                "description": "Fast download optimized for smaller file size and mobile devices.",
                "status": compact_fmt.get("status", "ready"),
                "status_reason": compact_fmt.get("status_reason"),
                "recommended": False
            })

        mp3_fmt = next((f for f in formats if f.get("format_id") == "best_audio_mp3"), None)
        if mp3_fmt or has_audio:
            sz_b = mp3_fmt.get("estimated_size_bytes") if mp3_fmt else None
            options.append({
                "action": "extract_audio_mp3",
                "format_type": "audio",
                "format_id": "best_audio_mp3",
                "resolution": "Audio Only",
                "codec": "MP3 (320 kbps)",
                "estimated_size": _format_size(sz_b),
                "label": "🎵 Universal MP3 Soundtrack (320 kbps)",
                "description": "High-bitrate standalone audio track, compatible with all music players.",
                "status": mp3_fmt.get("status", "ready") if mp3_fmt else "ready",
                "status_reason": mp3_fmt.get("status_reason") if mp3_fmt else None,
                "recommended": False
            })

        m4a_fmt = next((f for f in formats if f.get("format_id") == "best_audio_m4a"), None)
        if m4a_fmt:
            sz_b = m4a_fmt.get("estimated_size_bytes")
            options.append({
                "action": "extract_audio_aac",
                "format_type": "audio",
                "format_id": "best_audio_m4a",
                "resolution": "Audio Only",
                "codec": "AAC / M4A",
                "estimated_size": _format_size(sz_b),
                "label": "🎧 Studio Master AAC Audio (M4A)",
                "description": "Direct digital audio track with pristine frequency preservation.",
                "status": m4a_fmt.get("status", "ready"),
                "status_reason": m4a_fmt.get("status_reason"),
                "recommended": False
            })

        if not options:
            for f in formats[:4]:
                options.append({
                    "action": "download_file",
                    "format_type": f.get("file_type") or "document",
                    "format_id": f.get("format_id"),
                    "resolution": f.get("resolution") or "-",
                    "codec": f.get("codec") or f.get("mime_type"),
                    "estimated_size": _format_size(f.get("estimated_size_bytes")),
                    "label": f"📦 Download {f.get('quality_label', 'Original File')} ({f.get('mime_type')})",
                    "description": "Direct original asset download preserving native file integrity.",
                    "status": f.get("status", "ready"),
                    "status_reason": f.get("status_reason"),
                    "recommended": f == formats[0]
                })

    dur_str = f"{int(duration_seconds)}s ({int(duration_seconds // 60)}m {int(duration_seconds % 60)}s)" if duration_seconds else "Unknown"

    card_lines = [
        f"### 📥 Media Preview: {title}\n",
        f"▶️ **[Play / Watch Stream Preview in Browser]({video_playing_url})** *(supports range requests & inline 10s preview)*\n",
    ]
    if thumbnail_url:
        card_lines.append(f"![Thumbnail]({thumbnail_url})\n")

    card_lines.append("| Attribute | Specification |")
    card_lines.append("| :--- | :--- |")
    card_lines.append(f"| **Media Title** | {title} |")
    card_lines.append(f"| **Platform** | `{provider}` |")
    card_lines.append(f"| **Media Type** | `{'Video + Audio' if (has_video and has_audio) else ('Video' if has_video else ('Audio' if has_audio else 'Document/File'))}` |")
    card_lines.append(f"| **Duration** | {dur_str} |")
    card_lines.append(f"| **Live Stream Player** | [▶ Open Web Player Preview]({video_playing_url}) |\n")

    card_lines.append("### 📋 Probed Download Formats & Availability\n")
    card_lines.append("| # | Format Option | Resolution | Codec | Est. Size | Status | Action | Description |")
    card_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    for idx, opt in enumerate(options, 1):
        st = opt.get("status", "ready")
        rec_tag = " *(Recommended)*" if opt.get("recommended") and st == "ready" else ""
        if st == "ready":
            st_badge = "🟢 Ready"
            action_btn = "[⬇️ Download Ready]"
        elif st == "unavailable":
            st_badge = "🔴 Unavailable"
            action_btn = "[⛔ Disabled]"
        else:
            st_badge = "🟡 Unknown Size"
            action_btn = "[⚠️ Approval Needed]"

        card_lines.append(
            f"| {idx} | **{opt['label']}**{rec_tag} | `{opt.get('resolution', '-')}` | `{opt.get('codec', '-')}` | `{opt.get('estimated_size', '-')}` | {st_badge} | {action_btn} | {opt.get('description', '')} |"
        )

    if all_unavailable:
        card_lines.append(f"\n⚠️ **Notice**: All formats are currently unavailable because the backend adapter is unreachable or encountering platform restrictions ({options[0].get('status_reason') if options else 'Service offline'}).")
    else:
        card_lines.append("\n*To download, tell me which option you want (e.g. 'download compatible video', 'give me master video', or 'extract mp3 audio').*")

    interactive_card = "\n".join(card_lines)

    first_err = formats[0].get("status_reason") if (formats and all_unavailable) else None
    prompt_str = (
        f"Found '{title}', but media extraction failed: {first_err or 'Service is currently unavailable'}."
        if all_unavailable else
        f"Found '{title}'. Universal compatible video, native stream, and audio extraction are probed and ready. Would you like me to download the compatible video, native master, or extract MP3 audio?"
    )

    return make_success_envelope({
        "source_id": source_id,
        "url": url,
        "title": title,
        "thumbnail_url": thumbnail_url,
        "video_playing_url": video_playing_url,
        "stream_preview_url": video_playing_url,
        "duration_seconds": duration_seconds,
        "provider": provider,
        "has_video": has_video,
        "has_audio": has_audio,
        "options": options,
        "interactive_card": interactive_card,
        "prompt_to_user": prompt_str
    })

# =====================================================================
# MCP TOOL 12: acquire_media (Single-turn autonomous download)
# =====================================================================
async def acquire_media(
    url: str,
    format_type: str = "video",
    quality: str = "best",
    auto_approve: bool = True,
    api_key: Optional[str] = None,
    token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Autonomous single-turn acquisition: inspects, approves, downloads, verifies,
    and delivers direct streaming and signed download links in ONE tool call.
    """
    insp_res = await inspect_source(url, api_key=api_key, token=token)
    if not insp_res.get("success"):
        return insp_res

    data = insp_res.get("data", {})
    source_id = data.get("source_id")

    fmt_res = await list_formats(source_id, api_key=api_key, token=token)
    formats = fmt_res.get("data", {}).get("formats", [])
    if not formats:
        return make_error_envelope(code="NO_FORMATS", message="No downloadable formats discovered for this source.")

    f_type_low = format_type.lower()
    selected_format = None
    if f_type_low in {"audio", "mp3", "m4a", "soundtrack"}:
        selected_format = next((f for f in formats if f.get("format_id") == "best_audio_mp3"), None) or \
                          next((f for f in formats if f.get("format_id") == "best_audio_m4a"), None) or \
                          next((f for f in formats if f.get("file_type") == "audio"), None)
    elif f_type_low in {"video", "mp4", "clip"}:
        selected_format = next((f for f in formats if f.get("format_id") == "best_compatible_mp4"), None) or \
                          next((f for f in formats if f.get("format_id") == "best_video_audio"), None) or \
                          next((f for f in formats if f.get("file_type") == "video"), None)
    elif f_type_low in {"image", "gallery", "archive", "zip"}:
        selected_format = next((f for f in formats if f.get("file_type") in {"image", "archive"}), None)

    if not selected_format:
        selected_format = formats[0]

    format_id = selected_format.get("format_id")

    approval_id = None
    async with async_session_factory() as session:
        user, _ = await _resolve_user_from_credentials(session, api_key=api_key, token=token, required_permission="write")
        if auto_approve and user:
            approval = UserApproval(
                user_id=user.id,
                source_id=source_id,
                format_id=format_id,
                status=ApprovalStatus.APPROVED.value,
                estimated_size_bytes=selected_format.get("estimated_size_bytes") or 0,
                reason="Auto-approved by autonomous acquisition agent"
            )
            session.add(approval)
            await session.commit()
            await session.refresh(approval)
            approval_id = approval.id

    start_res = await start_acquisition(
        source_id=source_id,
        format_id=format_id,
        approval_id=approval_id,
        api_key=api_key,
        token=token
    )
    if not start_res.get("success"):
        return start_res

    start_data = start_res.get("data", {})
    job_id = start_data.get("job_id")
    artifact_id = start_data.get("artifact_id")

    from services.acquisition_worker.worker import AcquisitionWorker
    worker = AcquisitionWorker()

    start_time = asyncio.get_event_loop().time()
    while not artifact_id and (asyncio.get_event_loop().time() - start_time) < 90.0:
        await worker.process_next_job(target_job_id=job_id)

        status_res = await get_job_status(job_id, api_key=api_key, token=token)
        if status_res.get("success"):
            s_data = status_res.get("data", {})
            st = s_data.get("state")
            if st == "completed":
                artifact_id = s_data.get("artifact_id")
                break
            elif st in {"failed", "cancelled"}:
                return make_error_envelope(
                    code="ACQUISITION_FAILED",
                    message=s_data.get("error_message") or f"Job entered {st} state."
                )
        await asyncio.sleep(0.5)

    if not artifact_id:
        return make_error_envelope(
            code="TIMEOUT",
            message=f"Acquisition job '{job_id}' did not complete within the 90s deadline. Polling may be resumed with get_job_status."
        )

    return await get_artifact(artifact_id, api_key=api_key, token=token)

@mcp.tool(
    name="preview_media",
    description="Inspects any media URL or social post (YouTube, Instagram, TikTok, Twitter/X, Reddit, Vimeo, SoundCloud, PDF, ZIP), generates an inline playable preview, extracts metadata, and formats clear user choices for download."
)
async def _mcp_preview_media(url: str, ctx: Context) -> Dict[str, Any]:
    return await preview_media(url)

@mcp.tool(
    name="acquire_media",
    description="Autonomous single-turn acquisition: inspects, approves, downloads, verifies, and delivers direct streaming and signed download links in ONE tool call. Supports format_type: 'video' (MP4), 'audio' (MP3), 'image', 'document', or 'best'."
)
async def _mcp_acquire_media(
    url: str,
    ctx: Context,
    format_type: str = "video",
    quality: str = "best",
    auto_approve: bool = True
) -> Dict[str, Any]:
    return await acquire_media(url=url, format_type=format_type, quality=quality, auto_approve=auto_approve)

@mcp.tool(
    name="inspect_source",
    description="Inspects a URL or document source, checks SSRF safety and permissions, and returns metadata without downloading."
)
async def _mcp_inspect_source(
    url: str,
    ctx: Context,
    user_preferences: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    return await inspect_source(url, user_preferences)

@mcp.tool(
    name="list_formats",
    description="Lists downloadable formats for an inspected source."
)
async def _mcp_list_formats(source_id: str, ctx: Context) -> Dict[str, Any]:
    return await list_formats(source_id)

@mcp.tool(
    name="preflight_acquisition",
    description="Checks acquisition limits and whether user approval is required."
)
async def _mcp_preflight_acquisition(
    source_id: str,
    format_id: str,
    ctx: Context,
    execution_mode: str = "cloud"
) -> Dict[str, Any]:
    return await preflight_acquisition(source_id, format_id, execution_mode)

@mcp.tool(
    name="request_approval",
    description="Creates a user approval request for an acquisition."
)
async def _mcp_request_approval(
    source_id: str,
    format_id: str,
    reason: str,
    ctx: Context
) -> Dict[str, Any]:
    return await request_approval(source_id, format_id, reason)

@mcp.tool(
    name="start_acquisition",
    description="Queues an approved acquisition and returns its job ID."
)
async def _mcp_start_acquisition(
    source_id: str,
    format_id: str,
    ctx: Context,
    approval_id: Optional[str] = None,
    execution_mode: str = "cloud",
    delivery_target: Optional[Dict[str, Any]] = None,
    privacy: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    return await start_acquisition(
        source_id=source_id,
        format_id=format_id,
        approval_id=approval_id,
        execution_mode=execution_mode,
        delivery_target=delivery_target,
        privacy=privacy
    )

@mcp.tool(
    name="get_job_status",
    description="Returns progress for a job owned by the authenticated user."
)
async def _mcp_get_job_status(job_id: str, ctx: Context) -> Dict[str, Any]:
    return await get_job_status(job_id)

@mcp.tool(
    name="get_artifact",
    description="Returns verified metadata and an expiring download link for a user-owned artifact."
)
async def _mcp_get_artifact(artifact_id: str, ctx: Context) -> Dict[str, Any]:
    return await get_artifact(artifact_id)

@mcp.tool(
    name="get_user_dashboard_link",
    description="Returns the authenticated user's dashboard link. Requires a user portal credential; agent keys are refused."
)
async def _mcp_get_user_dashboard_link(
    ctx: Context,
    email: Optional[str] = None
) -> Dict[str, Any]:
    return await get_user_dashboard_link(email)

@mcp.tool(
    name="describe_capabilities",
    description="Returns the engine's capabilities, limits, active providers, supported media formats, rights policies, and operational status."
)
async def _mcp_describe_capabilities(ctx: Context) -> Dict[str, Any]:
    return await describe_capabilities()

@mcp.tool(
    name="search_sources",
    description="Searches for downloadable content, media streams, open films, archives, or datasets matching a natural language query or title. Returns candidate sources ready for format inspection or acquisition."
)
async def _mcp_search_sources(
    query: str,
    ctx: Context,
    kind: Optional[str] = None,
    max_results: int = 5
) -> Dict[str, Any]:
    return await search_sources(query=query, kind=kind, max_results=max_results)

async def run_server():
    """Initializes tables and starts MCP server over stdio."""
    await init_db()
    await mcp.run_stdio_async()

if __name__ == "__main__":
    asyncio.run(run_server())
