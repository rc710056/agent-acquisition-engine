import os
import shutil
import hashlib
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
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

    def generate_delivery_bundle(self, artifact_id: str, base_url: Optional[str] = None, ttl_seconds: Optional[int] = None) -> Dict[str, Any]:
        """
        Generates full delivery and preview links (download, inline preview, contact sheet) with signed token.
        """
        ttl = ttl_seconds or settings.EXPIRING_URL_TTL_SECONDS
        token = generate_signed_delivery_token(artifact_id, settings.SECRET_KEY, ttl_seconds=ttl)
        import os
        from apps.api.app import config
        api_base = (
            base_url
            or os.environ.get("API_BASE_URL")
            or config.PUBLIC_BASE_URL
            or settings.API_BASE_URL
        ).rstrip("/")
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        return {
            "token": token,
            "download_url": f"{api_base}/api/v1/delivery/download?token={token}&disposition=attachment",
            "preview_url": f"{api_base}/api/v1/delivery/download?token={token}&disposition=inline",
            "contact_sheet_url": f"{api_base}/api/v1/delivery/download?token={token}&view=contact_sheet&disposition=inline",
            "expires_at": expires_at
        }

    def generate_delivery_url(self, artifact_id: str, base_url: Optional[str] = None, ttl_seconds: Optional[int] = None) -> Tuple[str, datetime]:
        """
        Creates a time-bounded cryptographically signed download URL for an artifact.
        """
        bundle = self.generate_delivery_bundle(artifact_id, base_url=base_url, ttl_seconds=ttl_seconds)
        return bundle["download_url"], bundle["expires_at"]

    def generate_contact_sheet(self, video_path: Path, output_filename: Optional[str] = None) -> Optional[Path]:
        """
        Generates a 2x2 contact sheet tile thumbnail for a video artifact using ffmpeg.
        Returns the path to the generated image file, or None if failed.
        """
        if not video_path.exists():
            return None

        out_name = output_filename or f"{video_path.stem}_contact_sheet.jpg"
        out_path = self.artifacts_dir / out_name

        import subprocess
        # 1. Attempt 2x2 tiled contact sheet
        try:
            cmd = [
                "ffmpeg", "-y", "-i", str(video_path),
                "-vf", "select='not(mod(n\\,60))',scale=320:180,tile=2x2",
                "-frames:v", "1", "-q:v", "3",
                str(out_path)
            ]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
            if out_path.exists() and out_path.stat().st_size > 0:
                return out_path
        except Exception:
            pass

        # 2. Fallback to single frame snapshot
        try:
            cmd_fallback = [
                "ffmpeg", "-y", "-ss", "00:00:01", "-i", str(video_path),
                "-frames:v", "1", "-q:v", "3",
                str(out_path)
            ]
            subprocess.run(cmd_fallback, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            if out_path.exists() and out_path.stat().st_size > 0:
                return out_path
        except Exception:
            pass

        return None

    async def clean_expired_artifacts(self, session) -> int:
        """
        Deletes artifacts from disk and database whose retention TTL has expired.
        """
        from sqlalchemy import select
        from apps.api.app.models.entities import Artifact
        now = datetime.now(timezone.utc)
        stmt = select(Artifact).where(Artifact.expires_at.is_not(None), Artifact.expires_at <= now)
        res = await session.execute(stmt)
        expired = res.scalars().all()
        count = 0
        for art in expired:
            p = self.get_artifact_path(art.storage_path)
            if p and p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass
            await session.delete(art)
            count += 1
        if count > 0:
            await session.commit()
        return count

storage_service = StorageService()
