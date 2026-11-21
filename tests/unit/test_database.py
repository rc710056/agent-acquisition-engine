import pytest
import uuid
from sqlalchemy import select
from apps.api.app.models.database import engine, async_session_factory, init_db
from apps.api.app.models.entities import User, Source, SourceOption, AcquisitionJob

@pytest.mark.asyncio
async def test_database_init_and_crud():
    await init_db()

    async with async_session_factory() as session:
        # Create test user with unique email
        unique_email = f"agent_{uuid.uuid4().hex[:8]}@example.com"
        test_user = User(email=unique_email, hashed_password="hashed_pwd_123")
        session.add(test_user)
        await session.commit()
        await session.refresh(test_user)

        assert test_user.id is not None
        assert test_user.email == unique_email

        # Create test source
        test_source = Source(
            url="https://example.com/test.pdf",
            provider_id="direct_http",
            content_type="application/pdf",
            estimated_size_bytes=1024,
            is_permitted=True
        )
        session.add(test_source)
        await session.commit()
        await session.refresh(test_source)

        assert test_source.id is not None
        assert test_source.is_permitted is True

        # Query user
        stmt = select(User).where(User.email == unique_email)
        result = await session.execute(stmt)
        queried_user = result.scalar_one_or_none()
        assert queried_user is not None
        assert queried_user.id == test_user.id
