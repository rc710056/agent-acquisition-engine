import pytest
from httpx import AsyncClient, ASGITransport
from apps.api.app.main import app as fastapi_app
from apps.api.app.models.database import init_db
from apps.api.app.security.ssrf import SSRFValidator
from services.mcp_server.server import inspect_source

@pytest.mark.asyncio
async def test_ssrf_attack_prevention():
    await init_db()

    # Direct IP attack
    res1 = await inspect_source(url="http://127.0.0.1:8000/api/v1/health")
    assert res1["is_permitted"] is False
    assert any("forbidden" in err.lower() or "ssrf" in err.lower() or "prohibited" in err.lower() for err in res1["errors"])

    # AWS/GCP cloud metadata attack
    res2 = await inspect_source(url="http://169.254.169.254/latest/meta-data/")
    assert res2["is_permitted"] is False
    assert any(
        term in err.lower()
        for err in res2["errors"]
        for term in ("forbidden", "ssrf", "prohibited", "blocked network", "non-global")
    )

    # Loopback keyword attack
    res3 = await inspect_source(url="http://localhost:22")
    assert res3["is_permitted"] is False

    # Non-HTTP protocol injection attack
    res4 = await inspect_source(url="file:///etc/shadow")
    assert res4["is_permitted"] is False

@pytest.mark.asyncio
async def test_tampered_signed_download_token():
    await init_db()
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as client:
        # Submit fake / invalid token
        resp = await client.get("/api/v1/delivery/download?token=fake_tampered_token_string")
        assert resp.status_code == 403
        assert "access denied" in resp.json()["detail"].lower()
