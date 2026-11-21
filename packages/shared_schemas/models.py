from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime

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

class FormatOption(BaseModel):
    format_id: str
    file_type: str = "document" # document, image, video, audio, archive, binary
    mime_type: str
    resolution: Optional[str] = None
    codec: Optional[str] = None
    estimated_size_bytes: Optional[int] = None
    quality_label: str = "original"
    provider_restrictions: Optional[List[str]] = None

class SourceInspectionResponse(BaseModel):
    source_id: str
    url: str
    provider_id: str
    is_permitted: bool
    capabilities: List[str]
    mime_type: Optional[str] = None
    estimated_size_bytes: Optional[int] = None
    inspection_status: str
    errors: List[str] = []

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
    expires_at: datetime
