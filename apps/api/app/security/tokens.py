import hmac
import hashlib
import time
import base64
import json
from typing import Optional, Tuple

def generate_signed_delivery_token(artifact_id: str, secret_key: str, ttl_seconds: int = 3600) -> str:
    """
    Generates a URL-safe cryptographically signed expiring delivery token.
    Payload: {"art_id": artifact_id, "exp": timestamp}
    Format: base64(payload).base64(hmac)
    """
    expires_at = int(time.time()) + ttl_seconds
    payload_dict = {
        "art_id": artifact_id,
        "exp": expires_at
    }
    payload_bytes = json.dumps(payload_dict, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("=")

    sig = hmac.new(secret_key.encode("utf-8"), payload_bytes, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")

    return f"{payload_b64}.{sig_b64}"

def verify_signed_delivery_token(token: str, secret_key: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Verifies token signature and checks timestamp expiry.
    Returns (is_valid, artifact_id, error_reason).
    """
    if not token or "." not in token:
        return False, None, "Malformed delivery token format."

    parts = token.split(".", 1)
    payload_b64 = parts[0]
    sig_b64 = parts[1]

    # Re-pad base64
    payload_padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    sig_padded = sig_b64 + "=" * (-len(sig_b64) % 4)

    try:
        payload_bytes = base64.urlsafe_b64decode(payload_padded)
        if base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("=") != payload_b64:
            return False, None, "Non-canonical delivery token payload encoding."
        expected_sig = hmac.new(secret_key.encode("utf-8"), payload_bytes, hashlib.sha256).digest()
        actual_sig = base64.urlsafe_b64decode(sig_padded)
        if base64.urlsafe_b64encode(actual_sig).decode("ascii").rstrip("=") != sig_b64:
            return False, None, "Non-canonical delivery token signature encoding."
    except Exception as e:
        return False, None, f"Token decode failure: {str(e)}"

    if not hmac.compare_digest(expected_sig, actual_sig):
        return False, None, "Invalid cryptographic token signature."

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        return False, None, "Corrupted token payload."

    if not isinstance(payload, dict):
        return False, None, "Invalid delivery token payload."

    artifact_id = payload.get("art_id")
    expires_at = payload.get("exp")

    if not isinstance(artifact_id, str) or not artifact_id:
        return False, None, "Missing artifact identity in token."
    if type(expires_at) is not int:
        return False, None, "Invalid expiration in token."
    if time.time() >= expires_at:
        return False, None, "Delivery link has expired."

    return True, artifact_id, None

def hash_api_key(api_key: str) -> str:
    """Returns SHA-256 hash of API key for database lookup."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()
