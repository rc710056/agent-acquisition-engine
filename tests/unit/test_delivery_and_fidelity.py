import pytest
import asyncio
from pathlib import Path
import httpx
from httpx import AsyncClient, ASGITransport

from providers.direct_http.provider import DirectHTTPProvider, extract_filename_from_headers
from apps.api.app.services.verification import FileVerifier
from apps.api.app.main import app
from apps.api.app.models.database import async_session_factory, init_db
from apps.api.app.models.entities import Artifact, Source, User
from apps.api.app.services.storage import storage_service
from packages.shared_schemas.models import SourceType, SourceInspectionResponse


def test_extract_filename_mime_mapping():
    # 1. URL without extension + Content-Type: text/markdown -> .md
    headers_md = httpx.Headers({"content-type": "text/markdown; charset=utf-8"})
    assert extract_filename_from_headers(headers_md, "https://example.com/docs/readme") == "readme.md"

    # 2. URL without extension + Content-Type: text/csv -> .csv
    headers_csv = httpx.Headers({"content-type": "text/csv"})
    assert extract_filename_from_headers(headers_csv, "https://example.com/api/export") == "export.csv"

    # 3. URL without extension + Content-Type: application/json -> .json
    headers_json = httpx.Headers({"content-type": "application/json"})
    assert extract_filename_from_headers(headers_json, "https://example.com/api/v1/users") == "users.json"

    # 4. URL without extension + Content-Type: text/plain -> .txt
    headers_txt = httpx.Headers({"content-type": "text/plain"})
    assert extract_filename_from_headers(headers_txt, "https://example.com/log") == "log.txt"

    # 5. URL without extension + Content-Type: application/pdf -> .pdf
    headers_pdf = httpx.Headers({"content-type": "application/pdf"})
    assert extract_filename_from_headers(headers_pdf, "https://example.com/report") == "report.pdf"

    # 6. URL with existing extension is preserved
    headers_existing = httpx.Headers({"content-type": "application/octet-stream"})
    assert extract_filename_from_headers(headers_existing, "https://example.com/data.tar.gz") == "data.tar.gz"

    # 7. Content-Disposition takes precedence
    headers_cd = httpx.Headers({
        "content-type": "text/plain",
        "content-disposition": 'attachment; filename="custom_export.csv"'
    })
    assert extract_filename_from_headers(headers_cd, "https://example.com/download") == "custom_export.csv"


def test_text_file_verification_fidelity(tmp_path):
    # UTF-8 text files must not be downgraded to application/octet-stream

    # Markdown
    md_file = tmp_path / "test.md"
    md_file.write_text("# Markdown Title\nThis is a markdown file.", encoding="utf-8")
    res_md = FileVerifier.verify_file(md_file, expected_mime="text/markdown")
    assert res_md.is_valid is True
    assert res_md.detected_mime == "text/markdown"

    # CSV
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("id,name,value\n1,alice,100\n2,bob,200\n", encoding="utf-8")
    res_csv = FileVerifier.verify_file(csv_file, expected_mime="text/csv")
    assert res_csv.is_valid is True
    assert res_csv.detected_mime == "text/csv"

    # JSON
    json_file = tmp_path / "test.json"
    json_file.write_text('{"status": "ok", "count": 42}', encoding="utf-8")
    res_json = FileVerifier.verify_file(json_file, expected_mime="application/json")
    assert res_json.is_valid is True
    assert res_json.detected_mime == "application/json"

    # Plain Text
    txt_file = tmp_path / "test.txt"
    txt_file.write_text("Hello plain text world!", encoding="utf-8")
    res_txt = FileVerifier.verify_file(txt_file, expected_mime="text/plain")
    assert res_txt.is_valid is True
    assert res_txt.detected_mime == "text/plain"


@pytest.mark.asyncio
async def test_inspect_source_advance_approval_gate():
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Create fresh user session
        user_res = await ac.post("/api/v1/users/portal-link")
        assert user_res.status_code == 200
        token = user_res.json()["portal_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Direct HTTP file inspect
        res = await ac.post("/api/v1/sources/inspect", json={"url": "https://httpbin.org/bytes/1024"}, headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "requires_approval" in data
        assert "approval_reason" in data
        # For a small 1KB file, requires_approval should be False
        if data.get("estimated_size_bytes") and data["estimated_size_bytes"] <= 52_428_800:
            assert data["requires_approval"] is False
            assert data["approval_reason"] is None


@pytest.mark.asyncio
async def test_delivery_range_request_and_cors():
    import uuid
    await init_db()
    async with async_session_factory() as s:
        u_email = f"range_test_{uuid.uuid4().hex[:8]}@engine.io"
        u = User(email=u_email, hashed_password="pw", portal_token=f"pt_{uuid.uuid4().hex[:8]}", role="user")
        s.add(u)
        await s.flush()

        test_payload = b"abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        f = storage_service.artifacts_dir / "preview_video.mp4"
        f.write_bytes(test_payload)

        art = Artifact(
            user_id=u.id,
            filename="preview_video.mp4",
            mime_type="video/mp4",
            size_bytes=len(test_payload),
            sha256="dummy_sha",
            storage_path="preview_video.mp4",
            is_verified=True
        )
        s.add(art)
        await s.commit()
        art_id = art.id

    bundle = storage_service.generate_delivery_bundle(art_id)
    token = bundle["token"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Video streaming range request (206 Partial Content)
        res_range = await ac.get(
            f"/api/v1/delivery/download?token={token}&disposition=inline",
            headers={"Range": "bytes=0-9"}
        )
        assert res_range.status_code == 206
        assert res_range.headers.get("accept-ranges") == "bytes"
        assert res_range.headers.get("content-range") == f"bytes 0-9/{len(test_payload)}"
        assert res_range.content == test_payload[:10]
        assert "access-control-allow-origin" in res_range.headers
        assert "content-range" in res_range.headers.get("access-control-expose-headers", "").lower()

        # 2. Download endpoint attachment Content-Disposition
        res_dl = await ac.get(
            f"/api/v1/delivery/download?token={token}&disposition=attachment"
        )
        assert res_dl.status_code == 200
        cd = res_dl.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert 'filename="preview_video.mp4"' in cd

        # 3. OPTIONS preflight CORS check
        res_opt = await ac.options("/api/v1/delivery/download")
        assert res_opt.status_code == 200
        assert res_opt.headers.get("access-control-allow-origin") == "*"
        assert "access-control-expose-headers" in res_opt.headers
