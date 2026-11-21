import pytest
import time
from apps.api.app.security.ssrf import SSRFValidator
from apps.api.app.security.sanitization import sanitize_filename
from apps.api.app.security.tokens import generate_signed_delivery_token, verify_signed_delivery_token

def test_ssrf_validator_blocks_private_and_loopback():
    assert SSRFValidator.validate_url("http://127.0.0.1/admin")[0] is False
    assert SSRFValidator.validate_url("http://localhost:8080/secret")[0] is False
    assert SSRFValidator.validate_url("http://169.254.169.254/latest/meta-data/")[0] is False
    assert SSRFValidator.validate_url("http://10.0.0.1/private")[0] is False
    assert SSRFValidator.validate_url("http://192.168.1.1/router")[0] is False
    assert SSRFValidator.validate_url("http://172.16.5.4/db")[0] is False

def test_ssrf_validator_rejects_non_http_schemes():
    assert SSRFValidator.validate_url("file:///etc/passwd")[0] is False
    assert SSRFValidator.validate_url("ftp://ftp.example.com/test")[0] is False
    assert SSRFValidator.validate_url("gopher://127.0.0.1:70")[0] is False

def test_filename_sanitizer_path_traversal():
    assert sanitize_filename("../../../etc/passwd", "txt") == "passwd.txt"
    assert sanitize_filename("..\\..\\windows\\system32\\cmd.exe", "exe") == "cmd.exe"
    assert sanitize_filename("report?name=2024.pdf") == "report_name_2024.pdf"
    assert sanitize_filename("") != ""
    assert sanitize_filename("safe_document.pdf") == "safe_document.pdf"

def test_signed_delivery_tokens():
    secret = "test-secret-key-12345678901234567890"
    art_id = "art_test_999"

    token = generate_signed_delivery_token(art_id, secret, ttl_seconds=60)
    is_valid, verified_id, err = verify_signed_delivery_token(token, secret)
    assert is_valid is True
    assert verified_id == art_id
    assert err is None

    # Test tampering
    tampered = token[:-2] + "xx"
    is_valid, _, err = verify_signed_delivery_token(tampered, secret)
    assert is_valid is False

    # Test wrong secret
    is_valid, _, err = verify_signed_delivery_token(token, "different-secret-key")
    assert is_valid is False

    # Test expired token
    expired_token = generate_signed_delivery_token(art_id, secret, ttl_seconds=-10)
    is_valid, _, err = verify_signed_delivery_token(expired_token, secret)
    assert is_valid is False
    assert "expired" in err.lower()
