from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime

class SourceType(str, Enum):
    DIRECT_FILE = "DIRECT_FILE"
    WEBPAGE_WITH_MEDIA = "WEBPAGE_WITH_MEDIA"
    PLATFORM_MEDIA_PAGE = "PLATFORM_MEDIA_PAGE"
    MEDIA_COLLECTION = "MEDIA_COLLECTION"
    SHORT_URL = "SHORT_URL"
    DOCUMENT_PAGE = "DOCUMENT_PAGE"
    SOURCE_BLOCKED = "SOURCE_BLOCKED"
    UNSUPPORTED_SOURCE = "UNSUPPORTED_SOURCE"

class SecurityStatus(str, Enum):
    SAFE = "safe"
    BLOCKED = "blocked"
    REQUIRES_REVIEW = "requires_review"

class AcquisitionPermission(str, Enum):
    PERMITTED = "permitted"
    USER_AUTHORIZATION_REQUIRED = "user_authorization_required"
    RESTRICTED = "restricted"
    UNKNOWN = "unknown"

class SourceAccessStatus(str, Enum):
    ACCESSIBLE = "accessible"
    AUTHENTICATION_REQUIRED = "authentication_required"
    UNAVAILABLE = "unavailable"
    BLOCKED = "blocked"

class JobState(str, Enum):
    CREATED = "created"
    UNDERSTANDING = "understanding"
    DISCOVERING = "discovering"
    INSPECTING = "inspecting"
    NEEDS_CLARIFICATION = "needs_clarification"
    AWAITING_APPROVAL = "awaiting_approval"
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class ExecutionMode(str, Enum):
    CLOUD = "cloud"
    LOCAL = "local"

class SourceInspectionRequest(BaseModel):
    url: str
    user_preferences: Optional[Dict[str, Any]] = None

class MediaAsset(BaseModel):
    asset_id: str
    asset_type: str # video, audio, image, document, stream
    title: Optional[str] = None
    url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    mime_type: Optional[str] = None
    synopsis: Optional[str] = None
    director: Optional[str] = None
    cast: Optional[str] = None
    year: Optional[str] = None
    ott: Optional[List[Dict[str, Any]]] = None

class FormatOption(BaseModel):
    format_id: str
    file_type: str = "document" # document, image, video, audio, archive, binary
    mime_type: str
    resolution: Optional[str] = None
    codec: Optional[str] = None
    estimated_size_bytes: Optional[int] = None
    quality_label: str = "original"
    download_url: Optional[str] = None
    has_audio: Optional[bool] = None
    has_video: Optional[bool] = None
    category: Optional[str] = "recommended" # recommended, audio_only, video_only, raw
    provider_restrictions: Optional[List[str]] = []

class SourceInspectionResponse(BaseModel):
    source_id: str
    url: str
    resolved_url: Optional[str] = None
    source_type: SourceType = SourceType.DIRECT_FILE
    provider_id: str
    is_permitted: bool
    security_status: SecurityStatus = SecurityStatus.SAFE
    acquisition_permission: AcquisitionPermission = AcquisitionPermission.PERMITTED
    source_access_status: SourceAccessStatus = SourceAccessStatus.ACCESSIBLE
    capabilities: List[str] = []
    mime_type: Optional[str] = None
    estimated_size_bytes: Optional[int] = None
    inspection_status: str
    requires_approval: bool = False
    approval_reason: Optional[str] = None
    title: Optional[str] = None
    thumbnail_url: Optional[str] = None
    assets: List[MediaAsset] = []
    formats: List[FormatOption] = []
    errors: List[str] = []
    ott_channels: Optional[List[Dict[str, Any]]] = None
    ott: Optional[List[Dict[str, Any]]] = None
    synopsis: Optional[str] = None
    director: Optional[str] = None
    cast: Optional[str] = None
    year: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class PreflightRequest(BaseModel):
    source_id: str
    format_id: str
    execution_mode: ExecutionMode = ExecutionMode.CLOUD

class PreflightResponse(BaseModel):
    can_acquire: bool
    requires_approval: bool
    approval_reason: Optional[str] = None
    estimated_size_bytes: Optional[int] = None
    storage_available: bool = True
    duplicate_artifact_id: Optional[str] = None

class ApprovalRequestCreate(BaseModel):
    source_id: str
    format_id: str
    reason: str

class ApprovalResponse(BaseModel):
    approval_id: str
    status: ApprovalStatus
    message: str
    created_at: datetime

class CreateJobRequest(BaseModel):
    source_id: str
    format_id: str
    approval_id: Optional[str] = None
    execution_mode: ExecutionMode = ExecutionMode.CLOUD
    auto_approve: Optional[bool] = False

class JobStatusResponse(BaseModel):
    job_id: str
    state: JobState
    progress_percent: Optional[float] = 0.0
    bytes_transferred: int = 0
    total_bytes: Optional[int] = None
    current_operation: str
    artifact_id: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class ArtifactMetadata(BaseModel):
    artifact_id: str
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    is_verified: bool
    download_url: str
    preview_url: Optional[str] = None
    contact_sheet_url: Optional[str] = None
    preview_metadata: Optional[Dict[str, Any]] = None
    expires_at: datetime
