import pytest
import secrets
from pathlib import Path
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from apps.api.app.main import app
from apps.api.app.config import settings
from apps.api.app.models.database import async_session_factory
from apps.api.app.models.entities import User, AgentConnection, Source, SourceOption, AcquisitionJob, Artifact, UserApproval
from apps.api.app.security.tokens import hash_api_key
from packages.shared_schemas.models import JobState, ApprovalStatus

@pytest.fixture
async def setup_two_users():
    """Sets up User Alice and User Bob with isolated API keys."""
    async with async_session_factory() as session:
        uid = secrets.token_hex(4)
        # Create Alice
        alice = User(email=f"alice_{uid}@antigravity.internal", hashed_password="pwd", role="user")
        session.add(alice)
        await session.flush()

        alice_raw_key = f"aae_live_{secrets.token_urlsafe(32)}"
        alice_conn = AgentConnection(
            user_id=alice.id,
            agent_name="AliceClaudeAgent",
            api_key_hash=hash_api_key(alice_raw_key),
            permissions=["read", "acquire"]
        )
        session.add(alice_conn)

        # Create Bob
        bob = User(email=f"bob_{uid}@antigravity.internal", hashed_password="pwd", role="user")
        session.add(bob)
        await session.flush()

        bob_raw_key = f"aae_live_{secrets.token_urlsafe(32)}"
        bob_conn = AgentConnection(
            user_id=bob.id,
            agent_name="BobCursorAgent",
            api_key_hash=hash_api_key(bob_raw_key),
            permissions=["read", "acquire"]
        )
        session.add(bob_conn)

        # Create dummy source and options
        src1 = Source(
            url=f"https://example.com/alice_report_{uid}.pdf",
            canonical_url=f"https://example.com/alice_report_{uid}.pdf",
            source_type="DIRECT_FILE",
            provider_id="direct_http",
            content_type="application/pdf",
            estimated_size_bytes=1024,
            is_permitted=True
        )
        session.add(src1)
        await session.flush()
        opt1 = SourceOption(source_id=src1.id, format_id="original", mime_type="application/pdf", estimated_size_bytes=1024, quality_label="original")
        session.add(opt1)

        src2 = Source(
            url=f"https://example.com/bob_dataset_{uid}.zip",
            canonical_url=f"https://example.com/bob_dataset_{uid}.zip",
            source_type="DIRECT_FILE",
            provider_id="direct_http",
            content_type="application/zip",
            estimated_size_bytes=1024,
            is_permitted=True
        )
        session.add(src2)
        await session.flush()
        opt2 = SourceOption(source_id=src2.id, format_id="original", mime_type="application/zip", estimated_size_bytes=1024, quality_label="original")
        session.add(opt2)

        await session.commit()

        return {
            "alice": {"id": alice.id, "key": alice_raw_key, "source_id": src1.id},
            "bob": {"id": bob.id, "key": bob_raw_key, "source_id": src2.id}
        }

@pytest.mark.asyncio
async def test_job_isolation_between_users(setup_two_users):
    alice = setup_two_users["alice"]
    bob = setup_two_users["bob"]

    alice_headers = {"Authorization": f"Bearer {alice['key']}"}
    bob_headers = {"Authorization": f"Bearer {bob['key']}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Alice creates Job A
        res_a = await client.post("/api/v1/acquisitions/jobs", json={
            "source_id": alice["source_id"],
            "format_id": "original",
            "execution_mode": "cloud"
        }, headers=alice_headers)
        assert res_a.status_code == 201
        job_a_id = res_a.json()["job_id"]

        # Bob creates Job B
        res_b = await client.post("/api/v1/acquisitions/jobs", json={
            "source_id": bob["source_id"],
            "format_id": "original",
            "execution_mode": "cloud"
        }, headers=bob_headers)
        assert res_b.status_code == 201
        job_b_id = res_b.json()["job_id"]

        # 1. Alice lists jobs -> ONLY sees Job A
        alice_jobs_res = await client.get("/api/v1/acquisitions/jobs", headers=alice_headers)
        assert alice_jobs_res.status_code == 200
        alice_job_ids = [j["job_id"] for j in alice_jobs_res.json()]
        assert job_a_id in alice_job_ids
        assert job_b_id not in alice_job_ids, "Security breach: Alice can see Bob's job!"

        # 2. Bob lists jobs -> ONLY sees Job B
        bob_jobs_res = await client.get("/api/v1/acquisitions/jobs", headers=bob_headers)
        assert bob_jobs_res.status_code == 200
        bob_job_ids = [j["job_id"] for j in bob_jobs_res.json()]
        assert job_b_id in bob_job_ids
        assert job_a_id not in bob_job_ids, "Security breach: Bob can see Alice's job!"

        # 3. Cross-Tenant Job Access Denial
        # Alice attempts to fetch Bob's job details
        cross_res = await client.get(f"/api/v1/acquisitions/jobs/{job_b_id}", headers=alice_headers)
        assert cross_res.status_code == 404, "Security breach: Alice fetched Bob's job directly!"

        # Bob attempts to cancel Alice's job
        cross_cancel = await client.post(f"/api/v1/acquisitions/jobs/{job_a_id}/cancel", headers=bob_headers)
        assert cross_cancel.status_code == 404, "Security breach: Bob was able to cancel Alice's job!"

@pytest.mark.asyncio
async def test_approval_isolation_between_users(setup_two_users):
    alice = setup_two_users["alice"]
    bob = setup_two_users["bob"]

    alice_headers = {"Authorization": f"Bearer {alice['key']}"}
    bob_headers = {"Authorization": f"Bearer {bob['key']}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Alice requests approval
        req_res = await client.post("/api/v1/approvals/request", json={
            "source_id": alice["source_id"],
            "format_id": "original",
            "reason": "Alice research download"
        }, headers=alice_headers)
        assert req_res.status_code == 200
        approval_id = req_res.json()["approval_id"]

        # Alice lists approvals -> sees it
        alice_appr = await client.get("/api/v1/approvals", headers=alice_headers)
        assert any(a["approval_id"] == approval_id for a in alice_appr.json())

        # Bob lists approvals -> Bob CANNOT see Alice's approval
        bob_appr = await client.get("/api/v1/approvals", headers=bob_headers)
        assert not any(a["approval_id"] == approval_id for a in bob_appr.json())

        # Agent credentials cannot decide approvals, even for another user's request.
        bob_decide = await client.post(f"/api/v1/approvals/{approval_id}/decision", json={
            "decision": "approved"
        }, headers=bob_headers)
        assert bob_decide.status_code == 403

@pytest.mark.asyncio
async def test_artifact_isolation_and_deduplication(setup_two_users, tmp_path: Path):
    alice = setup_two_users["alice"]
    bob = setup_two_users["bob"]

    alice_headers = {"Authorization": f"Bearer {alice['key']}"}
    bob_headers = {"Authorization": f"Bearer {bob['key']}"}

    # Manually register an artifact owned by Alice
    async with async_session_factory() as session:
        art_a = Artifact(
            user_id=alice["id"],
            filename="alice_secret.pdf",
            mime_type="application/pdf",
            size_bytes=1024,
            sha256="abc123hash",
            storage_path="vault_alice_secret.pdf",
            is_verified=True,
            origin_cache_key="shared_cache_key_test_123"
        )
        session.add(art_a)
        await session.commit()
        art_a_id = art_a.id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Alice lists artifacts -> sees her artifact
        alice_arts = await client.get("/api/v1/artifacts", headers=alice_headers)
        assert any(a["artifact_id"] == art_a_id for a in alice_arts.json())

        # Bob lists artifacts -> does NOT see Alice's artifact
        bob_arts = await client.get("/api/v1/artifacts", headers=bob_headers)
        assert not any(a["artifact_id"] == art_a_id for a in bob_arts.json())

        # Bob attempts direct fetch of Alice's artifact -> 404
        direct_bob = await client.get(f"/api/v1/artifacts/{art_a_id}", headers=bob_headers)
        assert direct_bob.status_code == 404

@pytest.mark.asyncio
async def test_production_requests_require_credentials(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/acquisitions/jobs")
    assert response.status_code == 401
