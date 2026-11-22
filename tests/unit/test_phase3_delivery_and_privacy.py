import pytest
import asyncio
from pathlib import Path
from datetime import datetime, timezone, timedelta

from packages.provider_contracts.delivery_target import (
    LocalStorageTarget,
    EphemeralPassThroughTarget,
    S3PresignedTarget,
    DeliveryTargetFactory
)
from apps.api.app.services.storage import storage_service
from apps.api.app.security.tokens import verify_signed_delivery_token
from apps.api.app.config import settings
from apps.api.app.models.database import async_session_factory, init_db
from apps.api.app.models.entities import Artifact, User

@pytest.mark.asyncio
async def test_local_storage_target(tmp_path):
    target = LocalStorageTarget(storage_dir=str(tmp_path))
    handle = await target.prepare("test_video.mp4", size=1024)
    
    await target.put(handle, b"chunk_one_data")
    await target.put(handle, b"_chunk_two_data")
    
    result = await target.complete(handle, sha256="dummy")
    assert result["retained_on_engine_disk"] is True
    assert result["size_bytes"] == len(b"chunk_one_data_chunk_two_data")
    assert Path(result["destination"]).exists()
    assert Path(result["destination"]).read_bytes() == b"chunk_one_data_chunk_two_data"

@pytest.mark.asyncio
async def test_ephemeral_passthrough_target():
    target = EphemeralPassThroughTarget()
    handle = await target.prepare("stream.mp4", size=500)
    
    await target.put(handle, b"ephemeral_bytes_stream")
    result = await target.complete(handle, sha256="dummy")
    
    assert result["retained_on_engine_disk"] is False
    assert result["privacy_level"] == "level_2_pass_through_no_retention"
    assert result["size_bytes"] == len(b"ephemeral_bytes_stream")
    assert result["sha256"] is not None

@pytest.mark.asyncio
async def test_s3_presigned_target():
    target = S3PresignedTarget(upload_url="https://s3.amazonaws.com/my-bucket/sample.mp4")
    handle = await target.prepare("sample.mp4", size=2048)
    
    await target.put(handle, b"sample_s3_bytes")
    result = await target.complete(handle, sha256="dummy")
    
    assert result["retained_on_engine_disk"] is False
    assert result["s3_delivery_status"] == "transferred"
    assert result["size_bytes"] == len(b"sample_s3_bytes")

def test_delivery_target_factory():
    default_target = DeliveryTargetFactory.create(None)
    assert isinstance(default_target, LocalStorageTarget)
    
    ephemeral_target = DeliveryTargetFactory.create({"type": "ephemeral"})
    assert isinstance(ephemeral_target, EphemeralPassThroughTarget)
    
    privacy_target = DeliveryTargetFactory.create({"retention": "none"})
    assert isinstance(privacy_target, EphemeralPassThroughTarget)
    
    s3_target = DeliveryTargetFactory.create({"type": "s3", "upload_url": "https://s3.amazonaws.com/test"})
    assert isinstance(s3_target, S3PresignedTarget)

def test_generate_delivery_bundle():
    bundle = storage_service.generate_delivery_bundle("art_test_12345", ttl_seconds=600)
    assert "token" in bundle
    assert "disposition=attachment" in bundle["download_url"]
    assert "disposition=inline" in bundle["preview_url"]
    assert "view=contact_sheet" in bundle["contact_sheet_url"]
    assert bundle["expires_at"] > datetime.now(timezone.utc)
    
    # Verify the generated token
    is_valid, art_id, err = verify_signed_delivery_token(bundle["token"], settings.SECRET_KEY)
    assert is_valid is True
    assert art_id == "art_test_12345"

@pytest.mark.asyncio
async def test_clean_expired_artifacts(tmp_path):
    await init_db()
    async with async_session_factory() as session:
        import uuid
        test_filename = f"expired_test_{uuid.uuid4().hex[:8]}.txt"
        test_file = storage_service.artifacts_dir / test_filename
        test_file.write_text("should be deleted")
        
        user = User(
            email=f"expire_user_{datetime.now().timestamp()}@test.com",
            hashed_password="test_hashed_password",
            portal_token=f"pt_{datetime.now().timestamp()}",
            role="user"
        )
        session.add(user)
        await session.flush()
        
        expired_art = Artifact(
            user_id=user.id,
            filename=test_filename,
            mime_type="text/plain",
            size_bytes=17,
            sha256="dummy_hash",
            storage_path=test_filename,
            is_verified=True,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=2)
        )
        session.add(expired_art)
        await session.commit()
        art_id = expired_art.id

        # Clean expired
        deleted_count = await storage_service.clean_expired_artifacts(session)
        assert deleted_count >= 1
        
        # Verify artifact is gone from database and disk
        check = await session.get(Artifact, art_id)
        assert check is None
        assert not test_file.exists()

@pytest.mark.asyncio
async def test_delivery_download_inline_and_attachment_endpoints():
    from httpx import AsyncClient, ASGITransport
    from apps.api.app.main import app
    import uuid

    await init_db()
    async with async_session_factory() as session:
        test_filename = f"inline_test_{uuid.uuid4().hex[:8]}.txt"
        test_file = storage_service.artifacts_dir / test_filename
        test_file.write_text("Hello inline preview world!")
        
        user = User(
            email=f"delivery_user_{uuid.uuid4().hex[:8]}@test.com",
            hashed_password="hashed_pw",
            portal_token=f"pt_{uuid.uuid4().hex[:8]}",
            role="user"
        )
        session.add(user)
        await session.flush()
        
        art = Artifact(
            user_id=user.id,
            filename=test_filename,
            mime_type="text/plain",
            size_bytes=27,
            sha256="dummy_sha",
            storage_path=test_filename,
            is_verified=True
        )
        session.add(art)
        await session.commit()
        art_id = art.id

        bundle = storage_service.generate_delivery_bundle(art_id)
        token = bundle["token"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # 1. Inline disposition for preview
            res_inline = await ac.get(f"/api/v1/delivery/download?token={token}&disposition=inline")
            assert res_inline.status_code == 200
            assert "inline" in res_inline.headers.get("content-disposition", "")
            assert res_inline.headers.get("access-control-allow-origin") == "*"
            assert res_inline.headers.get("accept-ranges") == "bytes"
            assert res_inline.text == "Hello inline preview world!"

            # 2. Attachment disposition for download
            res_attach = await ac.get(f"/api/v1/delivery/download?token={token}&disposition=attachment")
            assert res_attach.status_code == 200
            assert "attachment" in res_attach.headers.get("content-disposition", "")
            assert res_attach.headers.get("access-control-allow-origin") == "*"
