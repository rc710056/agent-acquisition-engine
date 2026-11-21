import os
import shutil
import hashlib
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime, timezone, timedelta
from apps.api.app.config import settings
from apps.api.app.security.tokens import generate_signed_delivery_token
from apps.api.app.security.sanitization import sanitize_filename

class StorageService:
    """
    Manages physical artifact storage and secure signed delivery link generation.
    Enforces private storage by default, keeping raw filesystem paths inaccessible to agents.
    """

    def __init__(self, artifacts_dir: Optional[str] = None, temp_dir: Optional[str] = None):
        self.artifacts_dir = Path(artifacts_dir or settings.LOCAL_STORAGE_DIR).resolve()
        self.temp_dir = Path(temp_dir or settings.TEMP_STORAGE_DIR).resolve()

        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def get_temp_path(self, prefix: str = "temp") -> Path:
        """Returns a path for staging in-flight downloads."""
        import uuid
        filename = f"{prefix}_{uuid.uuid4().hex}.download"
        return self.temp_dir / filename

    def store_artifact(self, temp_path: Path, desired_filename: str) -> Tuple[Path, str, int, str]:
        """
        Moves a verified temporary download file into the permanent artifact vault.
        Returns (permanent_path, sanitized_filename, size_bytes, sha256_hash).
        """
        if not temp_path.exists():
            raise FileNotFoundError(f"Source temporary file not found at {temp_path}")

        sanitized_name = sanitize_filename(desired_filename)
        import uuid
        vault_name = f"{uuid.uuid4().hex[:12]}_{sanitized_name}"
        dest_path = self.artifacts_dir / vault_name

        # Calculate final SHA-256 and size while moving
        sha256 = hashlib.sha256()
        size_bytes = 0

        with open(temp_path, "rb") as src, open(dest_path, "wb") as dst:
            while chunk := src.read(65536):
                sha256.update(chunk)
                dst.write(chunk)
                size_bytes += len(chunk)

        # Remove temp file
        try:
            temp_path.unlink()
        except Exception:
            pass

        return dest_path, sanitized_name, size_bytes, sha256.hexdigest()

    def get_artifact_path(self, storage_path_or_filename: str) -> Optional[Path]:
        """Resolves an internal artifact path, ensuring no directory traversal."""
        candidate = Path(storage_path_or_filename)
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (self.artifacts_dir / storage_path_or_filename).resolve()

        # Ensure resolved path is strictly within artifacts_dir
        try:
            resolved.relative_to(self.artifacts_dir)
        except ValueError:
            return None

        if resolved.exists() and resolved.is_file():
            return resolved
        return None

    def generate_delivery_url(self, artifact_id: str, base_url: Optional[str] = None, ttl_seconds: Optional[int] = None) -> Tuple[str, datetime]:
        """
        Creates a time-bounded cryptographically signed download URL for an artifact.
        """
        ttl = ttl_seconds or settings.EXPIRING_URL_TTL_SECONDS
        token = generate_signed_delivery_token(artifact_id, settings.SECRET_KEY, ttl_seconds=ttl)
        api_base = (base_url or settings.API_BASE_URL).rstrip("/")
        download_url = f"{api_base}/api/v1/delivery/download?token={token}"
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        return download_url, expires_at

storage_service = StorageService()
