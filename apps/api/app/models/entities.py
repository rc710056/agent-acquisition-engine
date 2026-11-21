import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    BigInteger,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    Index
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

def generate_uuid() -> str:
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), default="user", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    agent_connections = relationship("AgentConnection", back_populates="user", cascade="all, delete-orphan")
    jobs = relationship("AcquisitionJob", back_populates="user", cascade="all, delete-orphan")
    artifacts = relationship("Artifact", back_populates="user", cascade="all, delete-orphan")
    approvals = relationship("UserApproval", back_populates="user", cascade="all, delete-orphan")

class AgentConnection(Base):
    __tablename__ = "agent_connections"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_name = Column(String(100), nullable=False)
    api_key_hash = Column(String(128), nullable=False, index=True)
    permissions = Column(JSON, default=lambda: ["read", "acquire"])
    last_active_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="agent_connections")

class Source(Base):
    __tablename__ = "sources"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    url = Column(Text, nullable=False)
    canonical_url = Column(Text, nullable=True)
    source_type = Column(String(50), default="DIRECT_FILE", nullable=False)
    provider_id = Column(String(50), nullable=False, index=True)
    content_type = Column(String(100), nullable=True)
    estimated_size_bytes = Column(BigInteger, nullable=True)
    is_permitted = Column(Boolean, default=True, nullable=False)
    security_status = Column(String(50), default="safe", nullable=False)
    acquisition_permission = Column(String(50), default="permitted", nullable=False)
    source_access_status = Column(String(50), default="accessible", nullable=False)
    title = Column(Text, nullable=True)
    thumbnail_url = Column(Text, nullable=True)
    assets_metadata = Column(JSON, nullable=True)
    inspection_status = Column(String(50), default="inspected", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    options = relationship("SourceOption", back_populates="source", cascade="all, delete-orphan")
    jobs = relationship("AcquisitionJob", back_populates="source")

class SourceOption(Base):
    __tablename__ = "source_options"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    source_id = Column(String(36), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    format_id = Column(String(100), nullable=False)
    file_type = Column(String(50), default="document", nullable=False)
    mime_type = Column(String(100), nullable=False)
    resolution = Column(String(50), nullable=True)
    codec = Column(String(50), nullable=True)
    estimated_size_bytes = Column(BigInteger, nullable=True)
    quality_label = Column(String(50), default="original", nullable=False)
    download_url = Column(Text, nullable=True)

    source = relationship("Source", back_populates="options")

class AcquisitionJob(Base):
    __tablename__ = "acquisition_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id = Column(String(36), ForeignKey("sources.id"), nullable=False, index=True)
    format_id = Column(String(100), nullable=False)
    execution_mode = Column(String(20), default="cloud", nullable=False)
    state = Column(String(50), default="created", nullable=False, index=True)
    progress_percent = Column(Float, default=0.0, nullable=False)
    bytes_transferred = Column(BigInteger, default=0, nullable=False)
    total_bytes = Column(BigInteger, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=3, nullable=False)
    next_retry_at = Column(DateTime, nullable=True, index=True)
    current_operation = Column(String(100), default="Job initialized", nullable=False)
    error_message = Column(Text, nullable=True)
    artifact_id = Column(String(36), ForeignKey("artifacts.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="jobs")
    source = relationship("Source", back_populates="jobs")
    artifact = relationship("Artifact", foreign_keys=[artifact_id])
    events = relationship("JobEvent", back_populates="job", cascade="all, delete-orphan")

class JobEvent(Base):
    __tablename__ = "job_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    job_id = Column(String(36), ForeignKey("acquisition_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    job = relationship("AcquisitionJob", back_populates="events")

class Artifact(Base):
    __tablename__ = "artifacts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    mime_type = Column(String(100), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    sha256 = Column(String(64), nullable=False, index=True)
    storage_path = Column(Text, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="artifacts")
    delivery_links = relationship("DeliveryLink", back_populates="artifact", cascade="all, delete-orphan")

class UserApproval(Base):
    __tablename__ = "user_approvals"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id = Column(String(36), ForeignKey("sources.id"), nullable=False)
    format_id = Column(String(100), nullable=False)
    status = Column(String(50), default="pending", nullable=False, index=True)
    reason = Column(Text, nullable=True)
    estimated_size_bytes = Column(BigInteger, nullable=True)
    decided_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="approvals")

class ProviderRegistry(Base):
    __tablename__ = "provider_registry"

    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)
    supported_schemes = Column(JSON, default=lambda: ["http", "https"])
    supported_domains = Column(JSON, default=list)
    version = Column(String(20), default="1.0.0")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

class UsageRecord(Base):
    __tablename__ = "usage_records"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id = Column(String(36), nullable=True)
    bytes_downloaded = Column(BigInteger, default=0, nullable=False)
    duration_seconds = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

class DeliveryLink(Base):
    __tablename__ = "delivery_links"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    artifact_id = Column(String(36), ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(128), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    download_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    artifact = relationship("Artifact", back_populates="delivery_links")
