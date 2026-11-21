import pytest
import tempfile
import zipfile
from pathlib import Path
from apps.api.app.services.verification import FileVerifier
from apps.api.app.services.storage import StorageService

def test_file_verifier_valid_text():
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"Hello Agent Acquisition Engine")
        temp_path = Path(f.name)

    try:
        res = FileVerifier.verify_file(temp_path)
        assert res.is_valid is True
        assert res.size_bytes == len(b"Hello Agent Acquisition Engine")
        assert len(res.sha256) == 64
        assert len(res.errors) == 0
    finally:
        temp_path.unlink()

def test_file_verifier_zero_byte():
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        pass
        temp_path = Path(f.name)

    try:
        res = FileVerifier.verify_file(temp_path)
        assert res.is_valid is False
        assert "0 bytes" in res.errors[0]
    finally:
        temp_path.unlink()

def test_file_verifier_valid_zip():
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
        temp_path = Path(f.name)

    with zipfile.ZipFile(temp_path, "w") as zf:
        zf.writestr("test.txt", "inside zip")

    try:
        res = FileVerifier.verify_file(temp_path)
        assert res.is_valid is True
        assert res.size_bytes > 0
        assert "application/zip" in res.detected_mime or "zip" in res.detected_mime
    finally:
        temp_path.unlink()

def test_file_verifier_html_disguised_as_pdf():
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"<!DOCTYPE html><html><body>404 Not Found</body></html>")
        temp_path = Path(f.name)

    try:
        res = FileVerifier.verify_file(temp_path)
        assert res.is_valid is False
        assert any("signature mismatch" in err.lower() for err in res.errors)
    finally:
        temp_path.unlink()

def test_storage_service_workflow():
    with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as art_dir:
        storage = StorageService(artifacts_dir=art_dir, temp_dir=temp_dir)

        # Stage temp file
        temp_file = storage.get_temp_path("test")
        with open(temp_file, "wb") as f:
            f.write(b"Acquired payload content")

        # Move to artifact vault
        perm_path, clean_name, size, sha = storage.store_artifact(temp_file, "my_report.pdf")

        assert perm_path.exists()
        assert clean_name == "my_report.pdf"
        assert size == len(b"Acquired payload content")
        assert not temp_file.exists()

        # Check retrieval
        resolved = storage.get_artifact_path(perm_path.name)
        assert resolved == perm_path

        # Traversal attempt must fail
        assert storage.get_artifact_path("../../../etc/passwd") is None
