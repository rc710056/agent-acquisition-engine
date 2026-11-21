import pytest
from httpx import AsyncClient, ASGITransport
from apps.api.app.main import app
from apps.api.app.models.database import init_db

@pytest.mark.asyncio
async def test_api_health():
    await init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

@pytest.mark.asyncio
async def test_api_agent_connection_creation():
    await init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/connections", json={"agent_name": "Claude-Research-Agent"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["agent_name"] == "Claude-Research-Agent"
        assert data["api_key"].startswith("aae_live_")

        # List connections
        list_resp = await client.get("/api/v1/connections")
        assert list_resp.status_code == 200
        connections = list_resp.json()
        assert any(c["agent_name"] == "Claude-Research-Agent" for c in connections)

@pytest.mark.asyncio
async def test_api_providers_list():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/providers")
        assert resp.status_code == 200
        providers = resp.json()
        assert len(providers) >= 1
        assert any(p["provider_id"] == "direct_http" for p in providers)
