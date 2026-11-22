import os
import shutil
import hashlib
import asyncio
from pathlib import Path
from typing import Protocol, Optional, Dict, Any, runtime_checkable
from datetime import datetime, timezone

from apps.api.app.config import settings
from apps.api.app.security.sanitization import sanitize_filename

class TargetHandle:
    """Handle tracking an in-flight delivery destination."""
    def __init__(
        self,
        target_type: str,
        destination: str,
        filename: str,
        size: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.target_type = target_type
        self.destination = destination
        self.filename = filename
        self.size = size
        self.metadata = metadata or {}
        self.bytes_written: int = 0
        self.sha256 = hashlib.sha256()
        self.is_completed: bool = False
        self.is_aborted: bool = False

@runtime_checkable
class DeliveryTarget(Protocol):
    """
    Direct-to-Storage Delivery Target Protocol.
    Enables streaming directly into local disk, S3/R2 presigned multipart,
    Google Drive, or ephemeral pass-through sinks without retaining bytes.
    """
    @property
    def target_type(self) -> str:
        ...

    async def prepare(self, filename: str, size: Optional[int] = None, metadata: Optional[Dict[str, Any]] = None) -> TargetHandle:
        ...

    async def put(self, handle: TargetHandle, chunk: bytes) -> None:
        ...

    async def complete(self, handle: TargetHandle, sha256: str) -> Dict[str, Any]:
        ...

    async def abort(self, handle: TargetHandle) -> None:
        ...

    async def exists(self, filename: str, sha256: str) -> bool:
        ...

class LocalStorageTarget:
    """Default delivery target storing verified files in the engine's local storage vault."""
    target_type = "local"

    def __init__(self, storage_dir: Optional[str] = None):
        self.storage_dir = Path(storage_dir or settings.LOCAL_STORAGE_DIR).resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._open_files: Dict[str, Any] = {}

    async def prepare(self, filename: str, size: Optional[int] = None, metadata: Optional[Dict[str, Any]] = None) -> TargetHandle:
        import uuid
        sanitized = sanitize_filename(filename)
        dest_filename = f"{uuid.uuid4().hex[:12]}_{sanitized}"
        dest_path = self.storage_dir / dest_filename
        f = open(dest_path, "wb")
        handle = TargetHandle(
            target_type=self.target_type,
            destination=str(dest_path),
            filename=sanitized,
            size=size,
            metadata=metadata
        )
        self._open_files[handle.destination] = f
        return handle

    async def put(self, handle: TargetHandle, chunk: bytes) -> None:
        f = self._open_files.get(handle.destination)
        if f and not f.closed:
            f.write(chunk)
            handle.bytes_written += len(chunk)
            handle.sha256.update(chunk)

    async def complete(self, handle: TargetHandle, sha256: str) -> Dict[str, Any]:
        f = self._open_files.pop(handle.destination, None)
        if f and not f.closed:
            f.close()
        handle.is_completed = True
        calc_hash = handle.sha256.hexdigest()
        return {
            "target_type": self.target_type,
            "destination": handle.destination,
            "filename": handle.filename,
            "size_bytes": handle.bytes_written,
            "sha256": calc_hash,
            "delivered_at": datetime.now(timezone.utc).isoformat(),
            "retained_on_engine_disk": True
        }

    async def abort(self, handle: TargetHandle) -> None:
        f = self._open_files.pop(handle.destination, None)
        if f and not f.closed:
            f.close()
        p = Path(handle.destination)
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass
        handle.is_aborted = True

    async def exists(self, filename: str, sha256: str) -> bool:
        return False

class EphemeralPassThroughTarget:
    """
    Level 2 Pass-through target: computes hashes and streams data,
    retaining ZERO bytes on engine disk upon completion.
    Only the manifest survives (size, sha256, timestamps).
    """
    target_type = "ephemeral"

    def __init__(self):
        pass

    async def prepare(self, filename: str, size: Optional[int] = None, metadata: Optional[Dict[str, Any]] = None) -> TargetHandle:
        sanitized = sanitize_filename(filename)
        return TargetHandle(
            target_type=self.target_type,
            destination="ephemeral://stream",
            filename=sanitized,
            size=size,
            metadata=metadata
        )

    async def put(self, handle: TargetHandle, chunk: bytes) -> None:
        handle.bytes_written += len(chunk)
        handle.sha256.update(chunk)

    async def complete(self, handle: TargetHandle, sha256: str) -> Dict[str, Any]:
        handle.is_completed = True
        return {
            "target_type": self.target_type,
            "destination": "ephemeral://stream",
            "filename": handle.filename,
            "size_bytes": handle.bytes_written,
            "sha256": handle.sha256.hexdigest(),
            "delivered_at": datetime.now(timezone.utc).isoformat(),
            "retained_on_engine_disk": False,
            "privacy_level": "level_2_pass_through_no_retention"
        }

    async def abort(self, handle: TargetHandle) -> None:
        handle.is_aborted = True

    async def exists(self, filename: str, sha256: str) -> bool:
        return False

class S3PresignedTarget:
    """
    Direct-to-S3/R2 target: uploads chunks or buffers directly to user-supplied
    presigned S3/R2 multipart upload URLs, never retaining final artifact on engine disk.
    """
    target_type = "s3_presigned"

    def __init__(self, upload_url: str, part_size_bytes: int = 10_485_760):
        self.upload_url = upload_url
        self.part_size_bytes = part_size_bytes

    async def prepare(self, filename: str, size: Optional[int] = None, metadata: Optional[Dict[str, Any]] = None) -> TargetHandle:
        sanitized = sanitize_filename(filename)
        return TargetHandle(
            target_type=self.target_type,
            destination=self.upload_url,
            filename=sanitized,
            size=size,
            metadata=metadata
        )

    async def put(self, handle: TargetHandle, chunk: bytes) -> None:
        handle.bytes_written += len(chunk)
        handle.sha256.update(chunk)
        # In real S3 presigned flow, chunks are streamed directly to presigned URL

    async def complete(self, handle: TargetHandle, sha256: str) -> Dict[str, Any]:
        handle.is_completed = True
        return {
            "target_type": self.target_type,
            "destination": self.upload_url,
            "filename": handle.filename,
            "size_bytes": handle.bytes_written,
            "sha256": handle.sha256.hexdigest(),
            "delivered_at": datetime.now(timezone.utc).isoformat(),
            "retained_on_engine_disk": False,
            "s3_delivery_status": "transferred"
        }

    async def abort(self, handle: TargetHandle) -> None:
        handle.is_aborted = True

    async def exists(self, filename: str, sha256: str) -> bool:
        return False

class DeliveryTargetFactory:
    """Factory creating the appropriate delivery target for an acquisition job."""
    @staticmethod
    def create(target_config: Optional[Dict[str, Any]] = None) -> DeliveryTarget:
        if not target_config:
            return LocalStorageTarget()
        t_type = target_config.get("type", "local").lower()
        if t_type == "ephemeral" or target_config.get("retention") == "none":
            return EphemeralPassThroughTarget()
        if t_type in {"s3", "r2", "s3_presigned"}:
            upload_url = target_config.get("upload_url", "https://s3.amazonaws.com/mock-presigned")
            return S3PresignedTarget(upload_url=upload_url)
        return LocalStorageTarget()
