import pytest
import asyncio
import secrets
import httpx
from datetime import datetime, timezone
from sqlalchemy import select

from apps.api.app.main import app
from apps.api.app.models.database import init_db, async_session_factory
from apps.api.app.models.entities import (
    User,
    AgentConnection,
    Source,
    SourceOption,
    AcquisitionJob,
    Artifact,
    UserApproval
)
from apps.api.app.security.tokens import hash_api_key
from services.mcp_server.server import (
    inspect_source,
    list_formats,
    preflight_acquisition,
    request_approval,
    start_acquisition,
    get_job_status,
    get_artifact,
    get_user_dashboard_link
)
from services.acquisition_worker.worker import AcquisitionWorker
from packages.shared_schemas.models import JobState, ApprovalStatus

# ==============================================================================
# PERSPECTIVE 1: USER PERSPECTIVE AUDIT
# ==============================================================================
@pytest.mark.asyncio
async def test_user_perspective_workspace_and_media():
    """
    Tests User Workspace:
    - Inspect Movie query ('Iron Man') -> Discovers OTT channels, multi-format options
    - Inspect Direct URL -> Slices & preflight checks
    - Inspect Magnet link -> Torrent provider routing
    - Health endpoint connectivity
    - Quota exhaustion enforcement (> 500 MB file rejected on preflight and job dispatch)
    """
    await init_db()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Health check verification (Vite proxy endpoint parity)
        h1 = await client.get("/health")
        assert h1.status_code == 200
        assert h1.json()["status"] == "healthy"

        h2 = await client.get("/api/v1/health")
        assert h2.status_code == 200
        assert h2.json()["status"] == "healthy"

        # 2. Movie Query Inspection
        movie_resp = await client.post("/api/v1/sources/inspect", json={"url": "Iron Man"})
        assert movie_resp.status_code == 200
        movie_data = movie_resp.json()
        assert movie_data["provider_id"] == "movie_intelligence"
        assert movie_data["is_permitted"] is True
        movie_source_id = movie_data["source_id"]

        # 3. Format Listing and Categorization
        fmts_resp = await client.get(f"/api/v1/sources/{movie_source_id}/formats")
        assert fmts_resp.status_code == 200
        formats = fmts_resp.json()
        assert len(formats) >= 3

        # Formats should prioritize synchronized video+audio
        best_fmt = formats[0]
        assert best_fmt["format_id"] == "best_video_audio"

        # 4. Oversized format quota check (4k_hdr_bluray = 5.24 GB > 500 MB limit)
        oversized_fmt = next((f for f in formats if f["format_id"] == "4k_hdr_bluray"), None)
        assert oversized_fmt is not None
        pf_over = await client.post("/api/v1/acquisitions/preflight", json={
            "source_id": movie_source_id,
            "format_id": oversized_fmt["format_id"]
        })
        assert pf_over.status_code == 200
        pf_over_data = pf_over.json()
        assert pf_over_data["can_acquire"] is False
        assert pf_over_data["storage_available"] is False
        assert "exceeds maximum engine quota limit" in pf_over_data["approval_reason"]

        # Attempting to create a job for an oversized format returns HTTP 413 / 400
        job_over = await client.post("/api/v1/acquisitions/jobs", json={
            "source_id": movie_source_id,
            "format_id": oversized_fmt["format_id"]
        })
        assert job_over.status_code in [400, 413]
        assert "exceeds maximum engine quota limit" in job_over.json()["detail"]

        # 5. Direct URL Inspection
        direct_resp = await client.post("/api/v1/sources/inspect", json={"url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3"})
        assert direct_resp.status_code == 200
        assert direct_resp.json()["is_permitted"] is True

        # 6. Magnet Link Inspection
        magnet_url = "magnet:?xt=urn:btih:3b245504fb5f4a4227cac320dbdc293a5b3f3f57&dn=Big+Buck+Bunny+1080p&tr=https%3A%2F%2Ftorrent.ubuntu.com%3A443%2Fannounce"
        mag_resp = await client.post("/api/v1/sources/inspect", json={"url": magnet_url})
        assert mag_resp.status_code == 200
        assert mag_resp.json()["provider_id"] == "torrent"

        # 7. Additional Movie inspection (Big Buck Bunny)
        bbb_resp = await client.post("/api/v1/sources/inspect", json={"url": "Big Buck Bunny"})
        assert bbb_resp.status_code == 200
        assert bbb_resp.json()["provider_id"] == "movie_intelligence"
        assert "Big Buck Bunny" in bbb_resp.json()["title"]

@pytest.mark.asyncio
async def test_user_perspective_jobs_vault_and_approvals():
    """
    Tests User perspective for:
    - Job dispatch and cancellation
    - Approvals gate (list, approve, reject)
    - Artifacts vault & signed download token streaming
    """
    await init_db()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Create fresh user session
        user_res = await client.post("/api/v1/users/portal-link")
        token = user_res.json()["portal_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create a source
        inspect_res = await client.post("/api/v1/sources/inspect", json={"url": "https://youtu.be/aqz-KE-bpKQ"}, headers=headers)
        assert inspect_res.status_code == 200
        assert inspect_res.json()["is_permitted"] is True
        source_id = inspect_res.json()["source_id"]

        # 2. Dispatch a Job
        job_create_res = await client.post("/api/v1/acquisitions/jobs", json={
            "source_id": source_id,
            "format_id": "best_video_audio",
            "auto_approve": True
        }, headers=headers)
        assert job_create_res.status_code == 201
        job_id = job_create_res.json()["job_id"]
        assert job_create_res.json()["state"] == "queued"

        # 3. List Jobs
        jobs_list = await client.get("/api/v1/acquisitions/jobs", headers=headers)
        assert jobs_list.status_code == 200
        assert any(j["job_id"] == job_id for j in jobs_list.json())

        # 4. Cancel Job
        cancel_res = await client.post(f"/api/v1/acquisitions/jobs/{job_id}/cancel", headers=headers)
        assert cancel_res.status_code == 200
        assert cancel_res.json()["state"] == "cancelled"

        # 5. Approvals Gate: Request & Decision
        appr_req = await client.post("/api/v1/approvals/request", json={
            "source_id": source_id,
            "format_id": "best_video_audio",
            "reason": "Test approval request"
        }, headers=headers)
        assert appr_req.status_code == 200, appr_req.text
        approval_id = appr_req.json()["approval_id"]

        # List Approvals
        apprs_list = await client.get("/api/v1/approvals", headers=headers)
        assert apprs_list.status_code == 200
        assert any(a["approval_id"] == approval_id for a in apprs_list.json())

        # Decide Approval: Approve
        decision_res = await client.post(f"/api/v1/approvals/{approval_id}/decision", json={"decision": "approved"}, headers=headers)
        assert decision_res.status_code == 200
        assert decision_res.json()["status"] == "approved"

        # 6. Artifact Vault: Verified Artifact Retrieval & Signed Download Link
        async with async_session_factory() as session:
            # Seed an artifact for this user
            from apps.api.app.services.storage import storage_service
            temp_path = storage_service.get_temp_path("test_artifact")
            temp_path.write_bytes(b"AAE Verified Test File Content 2026")
            perm_path, clean_name, size, sha = storage_service.store_artifact(temp_path, "verified_report.pdf")

            art = Artifact(
                user_id=user_res.json()["user_id"],
                filename=clean_name,
                mime_type="application/pdf",
                size_bytes=size,
                sha256=sha,
                storage_path=perm_path.name,
                is_verified=True
            )
            session.add(art)
            await session.commit()
            await session.refresh(art)
            art_id = art.id

        # List Artifacts
        artifacts_resp = await client.get("/api/v1/artifacts", headers=headers)
        assert artifacts_resp.status_code == 200
        user_artifacts = artifacts_resp.json()
        target_art = next((a for a in user_artifacts if a["artifact_id"] == art_id), None)
        assert target_art is not None
        assert target_art["is_verified"] is True
        assert target_art["sha256"] == sha
        download_url = target_art["download_url"]

        # Download artifact payload using signed expiring URL
        dl_path = download_url.replace("http://127.0.0.1:8000", "")
        dl_resp = await client.get(dl_path)
        assert dl_resp.status_code == 200
        assert dl_resp.content == b"AAE Verified Test File Content 2026"

# ==============================================================================
# PERSPECTIVE 2: AI AGENT PERSPECTIVE AUDIT
# ==============================================================================
@pytest.mark.asyncio
async def test_agent_perspective_mcp_and_security():
    """
    Tests AI Agent Perspective:
    - All 8 MCP protocol tools with api_key and token parameters
    - Agent authentication with bearer tokens / API keys
    - SSRF blocking
    - Quota exhaustion error handling (> 500 MB quota limit)
    - Approval gating enforcement
    - Multi-tenant isolation across MCP tools (Agent B cannot access Agent A's job or artifact)
    - Dynamic agent-owner dashboard URL resolution
    """
    await init_db()

    # 1. Create User A and Connected Agent Key A
    async with async_session_factory() as session:
        u_a = User(email=f"agent_owner_a_{secrets.token_hex(4)}@antigravity.internal", hashed_password="pwd", role="user")
        session.add(u_a)
        await session.flush()

        agent_key_a = f"aae_live_{secrets.token_urlsafe(32)}"
        conn_a = AgentConnection(
            user_id=u_a.id,
            agent_name="TestAutoAgentA",
            api_key_hash=hash_api_key(agent_key_a),
            permissions=["read", "acquire"]
        )
        session.add(conn_a)

        # Create User B and Connected Agent Key B
        u_b = User(email=f"agent_owner_b_{secrets.token_hex(4)}@antigravity.internal", hashed_password="pwd", role="user")
        session.add(u_b)
        await session.flush()

        agent_key_b = f"aae_live_{secrets.token_urlsafe(32)}"
        conn_b = AgentConnection(
            user_id=u_b.id,
            agent_name="TestAutoAgentB",
            api_key_hash=hash_api_key(agent_key_b),
            permissions=["read", "acquire"]
        )
        session.add(conn_b)
        await session.commit()

    # 2. Tool 1: inspect_source with agent key & permitted media target
    target_video_url = "https://youtu.be/jNQXAC9IVRw"
    inspect_res = await inspect_source(url=target_video_url, api_key=agent_key_a)
    assert inspect_res["is_permitted"] is True
    assert inspect_res["provider"] == "permitted_media"
    src_id = inspect_res["source_id"]

    # Tool 1 Error Path: invalid agent key rejected
    bad_inspect = await inspect_source(url=target_video_url, api_key="aae_live_invalid_key_999")
    assert bad_inspect["is_permitted"] is False
    assert "invalid" in bad_inspect["errors"][0].lower()

    # Tool 1 Error Path: SSRF target blocked
    ssrf_res = await inspect_source(url="http://169.254.169.254/latest/meta-data/", api_key=agent_key_a)
    assert ssrf_res["is_permitted"] is False
    assert ssrf_res["security_status"] == "blocked"

    # 3. Tool 2: list_formats with agent key
    fmts_res = await list_formats(source_id=src_id, api_key=agent_key_a)
    assert "formats" in fmts_res
    assert len(fmts_res["formats"]) > 0
    target_format = fmts_res["formats"][0]["format_id"]
    async with async_session_factory() as session:
        option_result = await session.execute(
            select(SourceOption).where(
                SourceOption.source_id == src_id,
                SourceOption.format_id == target_format
            )
        )
        option_result.scalar_one().estimated_size_bytes = 100_000_000
        await session.commit()

    # Tool 2 with invalid key rejected
    bad_fmts = await list_formats(source_id=src_id, api_key="aae_live_bad_key_999")
    assert "error" in bad_fmts

    # 4. Tool 3: preflight_acquisition with invalid key -> rejected
    pf_invalid_key = await preflight_acquisition(
        source_id=src_id,
        format_id=target_format,
        api_key="aae_live_invalid_bad_key_12345"
    )
    assert pf_invalid_key["can_acquire"] is False
    assert "invalid" in pf_invalid_key["error"].lower()

    # Tool 3: preflight with valid agent key -> success
    pf_valid = await preflight_acquisition(
        source_id=src_id,
        format_id=target_format,
        api_key=agent_key_a
    )
    assert pf_valid["can_acquire"] is True

    # Tool 3: Quota limit rejection check (> 500 MB)
    async with async_session_factory() as session:
        movie_src = await inspect_source("Iron Man")
        movie_src_id = movie_src["source_id"]
    pf_quota = await preflight_acquisition(
        source_id=movie_src_id,
        format_id="4k_hdr_bluray",
        api_key=agent_key_a
    )
    assert pf_quota["can_acquire"] is False
    assert "quota limit" in pf_quota["error"].lower()

    # 5. Tool 4: request_approval with agent key
    appr_res = await request_approval(
        source_id=src_id,
        format_id=target_format,
        reason="Large dataset acquisition requested by autonomous pipeline",
        api_key=agent_key_a
    )
    assert "approval_id" in appr_res
    appr_id = appr_res["approval_id"]

    # 6. Tool 5: start_acquisition with invalid agent key -> rejected
    start_bad_key = await start_acquisition(
        source_id=src_id,
        format_id=target_format,
        api_key="aae_live_invalid_bad_key"
    )
    assert "error" in start_bad_key

    # Tool 5: start_acquisition for oversized format -> rejected by quota
    start_quota = await start_acquisition(
        source_id=movie_src_id,
        format_id="4k_hdr_bluray",
        api_key=agent_key_a
    )
    assert "error" in start_quota
    assert "quota limit" in start_quota["error"].lower()

    # Tool 5 without approval -> rejected because format requires approval
    start_unapproved = await start_acquisition(
        source_id=src_id,
        format_id=target_format,
        api_key=agent_key_a
    )
    assert "error" in start_unapproved
    assert "approval is required" in start_unapproved["error"].lower()

    # Operator approves the request
    async with async_session_factory() as session:
        appr = await session.get(UserApproval, appr_id)
        appr.status = ApprovalStatus.APPROVED.value
        await session.commit()

    # Tool 5: start_acquisition with valid agent key and approved approval_id -> creates Job A
    start_res = await start_acquisition(
        source_id=src_id,
        format_id=target_format,
        approval_id=appr_id,
        api_key=agent_key_a
    )
    assert "job_id" in start_res
    job_a_id = start_res["job_id"]

    # 7. Tool 6: get_job_status with agent key
    status_res = await get_job_status(job_id=job_a_id, api_key=agent_key_a)
    assert status_res["job_id"] == job_a_id
    assert status_res["state"] in {"queued", "downloading", "completed"}

    # Tool 6 Multi-tenant isolation: Agent B cannot access Agent A's job status
    status_res_b = await get_job_status(job_id=job_a_id, api_key=agent_key_b)
    assert "error" in status_res_b
    assert "not found" in status_res_b["error"].lower() or "access denied" in status_res_b["error"].lower()

    # 8. Tool 7: get_artifact with agent key & multi-tenant isolation
    async with async_session_factory() as session:
        from apps.api.app.services.storage import storage_service
        temp_path = storage_service.get_temp_path("test_mcp_art")
        temp_path.write_bytes(b"Artifact Payload A for Agent A")
        perm_path, clean_name, size, sha = storage_service.store_artifact(temp_path, "agent_a_report.pdf")
        art_a = Artifact(
            user_id=u_a.id,
            filename=clean_name,
            mime_type="application/pdf",
            size_bytes=size,
            sha256=sha,
            storage_path=perm_path.name,
            is_verified=True
        )
        session.add(art_a)
        await session.commit()
        await session.refresh(art_a)
        art_a_id = art_a.id

    art_res_a = await get_artifact(artifact_id=art_a_id, api_key=agent_key_a)
    assert art_res_a["artifact_id"] == art_a_id
    assert art_res_a["is_verified"] is True
    assert "download_url" in art_res_a

    # Tool 7 Multi-tenant isolation: Agent B cannot access Agent A's artifact
    art_res_b = await get_artifact(artifact_id=art_a_id, api_key=agent_key_b)
    assert "error" in art_res_b
    assert "not found" in art_res_b["error"].lower() or "access denied" in art_res_b["error"].lower()

    # 9. Agent credentials cannot retrieve user portal credentials.
    dash_link_a = await get_user_dashboard_link(api_key=agent_key_a)
    assert "error" in dash_link_a
    assert "portal credential is required" in dash_link_a["error"].lower()

    dash_link_b = await get_user_dashboard_link(api_key=agent_key_b)
    assert "error" in dash_link_b

# ==============================================================================
# PERSPECTIVE 3: NEW USER PERSPECTIVE AUDIT
# ==============================================================================
@pytest.mark.asyncio
async def test_new_user_perspective_onboarding_and_isolation():
    """
    Tests New User Perspective:
    - First-time visitor without localStorage token -> Auto portal link provisioned
    - Malformed / invalid bearer token rejection (401 Unauthorized)
    - Workspace switching -> Create new workspace (/users/portal-link)
    - Workspace switching -> Enter existing token
    - Strict multi-user state isolation (User A vs User B)
    """
    await init_db()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Malformed / invalid token returns 401 Unauthorized
        bad_token_res = await client.get("/api/v1/users/me", headers={"Authorization": "Bearer malformed_bad_token_123"})
        assert bad_token_res.status_code == 401
        assert "Unrecognized token format" in bad_token_res.json()["detail"]

        # 2. First-time visitor without token provisioning dedicated workspace
        auto_user_res = await client.post("/api/v1/users/portal-link")
        assert auto_user_res.status_code == 200
        new_user = auto_user_res.json()
        assert new_user["portal_token"].startswith("aae_usr_")
        assert new_user["created"] is True
        token_a = new_user["portal_token"]
        user_a_id = new_user["user_id"]

        # 3. Authenticate as User A and create private job
        headers_a = {"Authorization": f"Bearer {token_a}"}
        src_res = await client.post("/api/v1/sources/inspect", json={"url": "https://youtu.be/aqz-KE-bpKQ"}, headers=headers_a)
        assert src_res.status_code == 200
        assert src_res.json()["is_permitted"] is True
        src_a_id = src_res.json()["source_id"]

        job_a_res = await client.post("/api/v1/acquisitions/jobs", json={
            "source_id": src_a_id,
            "format_id": "best_video_audio",
            "auto_approve": True
        }, headers=headers_a)
        assert job_a_res.status_code == 201
        job_a_id = job_a_res.json()["job_id"]

        # 4. User B switches workspace and provisions second user
        user_b_res = await client.post("/api/v1/users/portal-link", json={"email": "alice_switch@acme.org"})
        assert user_b_res.status_code == 200
        token_b = user_b_res.json()["portal_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # User B queries their profile
        profile_b = await client.get("/api/v1/users/me", headers=headers_b)
        assert profile_b.status_code == 200
        assert profile_b.json()["email"] == "alice_switch@acme.org"

        # 5. Strict isolation: User B cannot see User A's jobs
        jobs_b = await client.get("/api/v1/acquisitions/jobs", headers=headers_b)
        assert jobs_b.status_code == 200
        assert not any(j["job_id"] == job_a_id for j in jobs_b.json())

        # User B cannot directly access User A's job -> 404 Not Found
        direct_job_res = await client.get(f"/api/v1/acquisitions/jobs/{job_a_id}", headers=headers_b)
        assert direct_job_res.status_code == 404

        # 6. Switching back to User A's token restores User A's jobs
        jobs_a = await client.get("/api/v1/acquisitions/jobs", headers=headers_a)
        assert jobs_a.status_code == 200
        assert any(j["job_id"] == job_a_id for j in jobs_a.json())
