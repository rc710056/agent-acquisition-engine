import pytest
import pytest_asyncio
import httpx
import secrets
from sqlalchemy import select

from apps.api.app.main import app
from apps.api.app.models.database import async_session_factory
from apps.api.app.models.entities import User, AcquisitionJob
from services.mcp_server.server import get_user_dashboard_link

@pytest.mark.asyncio
async def test_get_or_create_portal_link():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create a user via portal-link endpoint
        test_email = f"user_{secrets.token_hex(4)}@antigravity.internal"
        resp = await client.post("/api/v1/users/portal-link", json={"email": test_email})
        assert resp.status_code == 200
        data = resp.json()

        assert data["email"] == test_email
        assert data["portal_token"].startswith("aae_usr_")
        assert f"token={data['portal_token']}" in data["dashboard_url"]
        assert data["created"] is True

        user_token = data["portal_token"]

        # 2. Authenticate using Bearer header with portal_token
        auth_headers = {"Authorization": f"Bearer {user_token}"}
        me_resp = await client.get("/api/v1/users/me", headers=auth_headers)
        assert me_resp.status_code == 200
        me_data = me_resp.json()
        assert me_data["email"] == test_email
        assert me_data["portal_token"] == user_token
        assert me_data["active_jobs_count"] == 0

        # 3. Authenticate using Query Parameter ?token=...
        query_resp = await client.get(f"/api/v1/users/me?token={user_token}")
        assert query_resp.status_code == 200
        query_data = query_resp.json()
        assert query_data["email"] == test_email

@pytest.mark.asyncio
async def test_portal_token_multi_user_isolation():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Create User Alice
        alice_resp = await client.post("/api/v1/users/portal-link", json={"email": f"alice_{secrets.token_hex(4)}@antigravity.internal"})
        alice_token = alice_resp.json()["portal_token"]
        alice_id = alice_resp.json()["user_id"]

        # Create User Bob
        bob_resp = await client.post("/api/v1/users/portal-link", json={"email": f"bob_{secrets.token_hex(4)}@antigravity.internal"})
        bob_token = bob_resp.json()["portal_token"]
        bob_id = bob_resp.json()["user_id"]

        # Create a job owned by Alice in the database
        async with async_session_factory() as session:
            job_alice = AcquisitionJob(
                user_id=alice_id,
                source_id="src_dummy",
                format_id="best_video",
                state="downloading",
                progress_percent=45.0,
                current_operation="Downloading chunks"
            )
            session.add(job_alice)
            await session.commit()
            await session.refresh(job_alice)
            job_alice_id = job_alice.id

        # Alice checks jobs via query token
        alice_jobs_resp = await client.get(f"/api/v1/acquisitions/jobs?token={alice_token}")
        assert alice_jobs_resp.status_code == 200
        alice_jobs = alice_jobs_resp.json()
        assert any(j["job_id"] == job_alice_id for j in alice_jobs)

        # Bob checks jobs via query token -> MUST NOT see Alice's job
        bob_jobs_resp = await client.get(f"/api/v1/acquisitions/jobs?token={bob_token}")
        assert bob_jobs_resp.status_code == 200
        bob_jobs = bob_jobs_resp.json()
        assert not any(j["job_id"] == job_alice_id for j in bob_jobs)

        # Bob attempts direct access to Alice's job -> Returns 404
        bob_direct_resp = await client.get(f"/api/v1/acquisitions/jobs/{job_alice_id}?token={bob_token}")
        assert bob_direct_resp.status_code == 404

@pytest.mark.asyncio
async def test_mcp_get_user_dashboard_link_tool():
    test_email = f"agent_user_{secrets.token_hex(4)}@antigravity.internal"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        portal = await client.post("/api/v1/users/portal-link", json={"email": test_email})
    result = await get_user_dashboard_link(
        email=test_email,
        token=portal.json()["portal_token"]
    )

    assert "dashboard_url" in result
    assert "how_it_works_url" in result
    assert result["portal_token"].startswith("aae_usr_")
    assert f"token={result['portal_token']}" in result["dashboard_url"]
    assert "tab=how-it-works" in result["how_it_works_url"]
