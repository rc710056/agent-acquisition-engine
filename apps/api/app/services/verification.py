import hashlib
import zipfile
import tarfile
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import filetype

# Well-known magic byte signatures for common acquired file types
MAGIC_SIGNATURES = {
    "pdf": b"%PDF-",
    "png": b"\x89PNG\r\n\x1a\n",
    "jpeg": b"\xff\xd8\xff",
    "jpg": b"\xff\xd8\xff",
    "gif": b"GIF8",
    "zip": b"PK\x03\x04",
    "gzip": b"\x1f\x8b",
    "gz": b"\x1f\x8b",
    "tar": b"ustar", # typically at byte offset 257
    "sqlite": b"SQLite format 3\x00",
}

class VerificationResult:
    def __init__(
        self,
        is_valid: bool,
        size_bytes: int,
        sha256: str,
        detected_mime: str,
        errors: list[str] = None,
        warnings: list[str] = None
    ):
        self.is_valid = is_valid
        self.size_bytes = size_bytes
        self.sha256 = sha256
        self.detected_mime = detected_mime
        self.errors = errors or []
        self.warnings = warnings or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "detected_mime": self.detected_mime,
            "errors": self.errors,
            "warnings": self.warnings
        }

class FileVerifier:
    """
    Performs comprehensive multi-stage integrity and format verification
    on acquired artifacts before completing an acquisition job.
    """

    @classmethod
    def verify_file(
        cls,
        file_path: Path,
        expected_size: Optional[int] = None,
        expected_mime: Optional[str] = None,
        expected_sha256: Optional[str] = None,
        expected_file_type: Optional[str] = None
    ) -> VerificationResult:
        errors: list[str] = []
        warnings: list[str] = []

        # 1. Existence check
        if not file_path.exists() or not file_path.is_file():
            return VerificationResult(
                is_valid=False,
                size_bytes=0,
                sha256="",
                detected_mime="unknown",
                errors=["File does not exist on disk."]
            )

        # 2. Non-zero byte check
        actual_size = file_path.stat().st_size
        if actual_size == 0:
            return VerificationResult(
                is_valid=False,
                size_bytes=0,
                sha256="",
                detected_mime="unknown",
                errors=["File size is 0 bytes (empty transfer)."]
            )

        # 3. Expected size comparison
        if expected_size is not None and expected_size > 0:
            if actual_size != expected_size:
                errors.append(f"Size mismatch: expected {expected_size} bytes, got {actual_size} bytes.")

        # 4. Checksum calculation
        sha256_hasher = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                while chunk := f.read(65536):
                    sha256_hasher.update(chunk)
            calculated_sha256 = sha256_hasher.hexdigest()
        except Exception as e:
            return VerificationResult(
                is_valid=False,
                size_bytes=actual_size,
                sha256="",
                detected_mime="unknown",
                errors=[f"Failed to read file for hashing: {str(e)}"]
            )

        if expected_sha256 and calculated_sha256.lower() != expected_sha256.lower():
            errors.append(f"Checksum mismatch: expected {expected_sha256}, got {calculated_sha256}.")

        # 5. MIME and Magic byte inspection
        ext = file_path.suffix.lower().lstrip(".")
        detected_mime = "application/octet-stream"
        kind = filetype.guess(str(file_path))
        if kind and kind.mime != "application/octet-stream":
            detected_mime = kind.mime
        else:
            # For text-like files (text/*, application/json, application/csv),
            # filetype.guess returns None. Check if valid UTF-8 and use expected or extension-derived MIME.
            is_valid_utf8 = False
            try:
                with open(file_path, "rb") as f:
                    sample = f.read(262144)
                sample.decode("utf-8")
                is_valid_utf8 = True
            except (UnicodeDecodeError, Exception):
                is_valid_utf8 = False

            text_ext_mimes = {
                "md": "text/markdown",
                "markdown": "text/markdown",
                "txt": "text/plain",
                "text": "text/plain",
                "csv": "text/csv",
                "tsv": "text/tab-separated-values",
                "json": "application/json",
                "jsonl": "application/x-ndjson",
                "ndjson": "application/x-ndjson",
                "xml": "application/xml",
                "html": "text/html",
                "htm": "text/html",
                "yaml": "text/yaml",
                "yml": "text/yaml",
                "js": "text/javascript",
                "ts": "text/typescript",
                "py": "text/x-python",
                "css": "text/css",
                "sh": "text/x-shellscript",
                "sql": "text/x-sql",
            }

            if is_valid_utf8:
                if expected_mime and (
                    expected_mime.startswith("text/")
                    or expected_mime in {
                        "application/json",
                        "application/csv",
                        "application/xml",
                        "application/javascript",
                        "application/x-ndjson"
                    }
                ):
                    detected_mime = expected_mime
                elif ext in text_ext_mimes:
                    detected_mime = text_ext_mimes[ext]
                elif expected_file_type == "text":
                    detected_mime = "text/plain"
                elif ext in {"txt", "csv", "json", "md"}:
                    detected_mime = text_ext_mimes.get(ext, "text/plain")
                else:
                    detected_mime = "text/plain"
            else:
                detected_mime = "application/octet-stream"

        # Read first 512 bytes for header signature verification
        try:
            with open(file_path, "rb") as f:
                header = f.read(512)
        except Exception as e:
            header = b""
            warnings.append(f"Could not read file header: {str(e)}")

        if ext in MAGIC_SIGNATURES:
            sig = MAGIC_SIGNATURES[ext]
            if not header.startswith(sig):
                # Special case for tar where signature is offset
                if ext == "tar" and len(header) >= 262 and header[257:262] == b"ustar":
                    pass
                else:
                    errors.append(
                        f"File header signature mismatch for .{ext} file. Expected {sig[:8]!r}, got {header[:8]!r}."
                    )

        # 6. Archive integrity test
        if ext == "zip":
            try:
                with zipfile.ZipFile(file_path, "r") as zf:
                    bad_file = zf.testzip()
                    if bad_file:
                        errors.append(f"Corrupted zip entry found: {bad_file}")
            except zipfile.BadZipFile:
                errors.append("Invalid or corrupted ZIP archive.")
            except Exception as e:
                warnings.append(f"ZIP validation warning: {str(e)}")

        # 7. Video stream presence check
        is_video_expected = expected_file_type == "video" or (expected_mime and expected_mime.startswith("video/"))
        if is_video_expected:
            if detected_mime.startswith("audio/"):
                errors.append(f"MIME conflict: Expected video format ({expected_mime or 'video'}), but file is an audio stream ({detected_mime}).")
            if ext in {"m4a", "mp3", "aac", "wav", "flac", "ogg", "opus"}:
                errors.append(f"Extension conflict: .{ext} is an audio format, but video stream was expected.")

            import shutil
            import subprocess
            ffprobe_bin = shutil.which("ffprobe")
            if ffprobe_bin:
                try:
                    probe = subprocess.run(
                        [ffprobe_bin, "-v", "error", "-select_streams", "v", "-show_entries", "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if probe.returncode == 0:
                        if not probe.stdout.strip():
                            errors.append("Integrity verification failed: Artifact contains 0 video streams (audio-only).")
                    else:
                        errors.append(f"Integrity verification failed: Could not detect valid video stream in file.")
                except Exception as probe_err:
                    warnings.append(f"ffprobe video stream check warning: {str(probe_err)}")

        is_valid = len(errors) == 0
        return VerificationResult(
            is_valid=is_valid,
            size_bytes=actual_size,
            sha256=calculated_sha256,
            detected_mime=detected_mime,
            errors=errors,
            warnings=warnings
        )
