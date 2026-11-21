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

@pytest.mark.asyncio
async def test_api_acquisitions_unknown_size_requires_approval():
    await init_db()
    import uuid
    from apps.api.app.models.database import async_session_factory
    from apps.api.app.models.entities import Source, SourceOption, User

    uid = uuid.uuid4().hex[:8]
    test_token = f"aae_usr_{uid}"
    async with async_session_factory() as session:
        user = User(
            email=f"api_test_{uid}@engine.io",
            hashed_password="pw",
            role="user",
            portal_token=test_token
        )
        session.add(user)
        src = Source(
            url=f"https://example.com/unknown_media_{uid}.mp4",
            provider_id="direct_http",
            content_type="video/mp4",
            estimated_size_bytes=None,
            is_permitted=True
        )
        session.add(src)
        await session.flush()

        opt = SourceOption(
            source_id=src.id,
            format_id="original",
            file_type="video",
            mime_type="video/mp4",
            estimated_size_bytes=None,
            quality_label="original"
        )
        session.add(opt)
        await session.commit()
        src_id = src.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {test_token}"}
        # Attempt to create acquisition job without approval_id
        resp = await client.post(
            "/api/v1/acquisitions/jobs",
            headers=headers,
            json={
                "source_id": src_id,
                "format_id": "original",
                "auto_approve": False
            }
        )
        assert resp.status_code == 403
        data = resp.json()
        assert "operator approval is required" in data["detail"].lower()

@pytest.mark.asyncio
async def test_api_sources_search_discovery():
    await init_db()
    import uuid
    from apps.api.app.models.database import async_session_factory
    from apps.api.app.models.entities import User

    uid = uuid.uuid4().hex[:8]
    test_token = f"aae_usr_{uid}"
    async with async_session_factory() as session:
        user = User(
            email=f"search_test_{uid}@engine.io",
            hashed_password="pw",
            role="user",
            portal_token=test_token
        )
        session.add(user)
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {test_token}"}
        resp = await client.get("/api/v1/sources/search?query=Elephants+Dream&kind=video&limit=2", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["results_count"] >= 1
        assert "candidates" in data

