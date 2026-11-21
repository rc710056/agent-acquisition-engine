import re
import os
import uuid
from pathlib import Path

# Safe characters: letters, digits, dots, underscores, hyphens
SAFE_FILENAME_REGEX = re.compile(r'[^a-zA-Z0-9._-]')

def sanitize_filename(filename: str, fallback_ext: str = "bin", max_length: int = 120) -> str:
    """
    Sanitizes an untrusted filename extracted from Content-Disposition or URL path:
    - Strips directory components and traversal sequences (../, ..\\)
    - Replaces unsafe characters with underscores
    - Avoids hidden files (leading dots)
    - Truncates to max_length while preserving extension
    - Fallbacks to a safe default if empty
    """
    if not filename:
        return f"acquisition_{uuid.uuid4().hex[:8]}.{fallback_ext}"

    # Extract basename only
    base = os.path.basename(filename)
    # Remove null bytes
    base = base.replace("\x00", "")

    # Replace unsafe chars
    clean = SAFE_FILENAME_REGEX.sub("_", base)

    # Avoid leading dots (hidden files on Unix)
    clean = clean.lstrip(".")

    if not clean:
        clean = f"file_{uuid.uuid4().hex[:8]}"

    # Split extension
    parts = clean.rsplit(".", 1)
    name_part = parts[0]
    ext_part = parts[1] if len(parts) > 1 else fallback_ext

    # Truncate name_part if needed
    if len(name_part) > max_length:
        name_part = name_part[:max_length]

    return f"{name_part}.{ext_part}"
