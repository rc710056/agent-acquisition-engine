from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from apps.api.app.config import settings
from apps.api.app.models.entities import Base

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=(settings.LOG_LEVEL.upper() == "DEBUG"),
    future=True
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

async def init_db() -> None:
    """Initializes database tables if they do not exist and runs safe column additions."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        def _check_and_add_columns(connection):
            from sqlalchemy import inspect, text
            inspector = inspect(connection)
            if "users" in inspector.get_table_names():
                cols = [c["name"] for c in inspector.get_columns("users")]
                if "portal_token" not in cols:
                    connection.execute(text("ALTER TABLE users ADD COLUMN portal_token VARCHAR(128)"))
            if "sources" in inspector.get_table_names():
                cols = [c["name"] for c in inspector.get_columns("sources")]
                if "source_type" not in cols:
                    connection.execute(text("ALTER TABLE sources ADD COLUMN source_type VARCHAR(50) DEFAULT 'DIRECT_FILE' NOT NULL"))
                if "security_status" not in cols:
                    connection.execute(text("ALTER TABLE sources ADD COLUMN security_status VARCHAR(50) DEFAULT 'safe' NOT NULL"))
                if "acquisition_permission" not in cols:
                    connection.execute(text("ALTER TABLE sources ADD COLUMN acquisition_permission VARCHAR(50) DEFAULT 'permitted' NOT NULL"))
                if "source_access_status" not in cols:
                    connection.execute(text("ALTER TABLE sources ADD COLUMN source_access_status VARCHAR(50) DEFAULT 'accessible' NOT NULL"))
                if "title" not in cols:
                    connection.execute(text("ALTER TABLE sources ADD COLUMN title TEXT"))
                if "thumbnail_url" not in cols:
                    connection.execute(text("ALTER TABLE sources ADD COLUMN thumbnail_url TEXT"))
                if "assets_metadata" not in cols:
                    connection.execute(text("ALTER TABLE sources ADD COLUMN assets_metadata JSON"))
            if "source_options" in inspector.get_table_names():
                cols = [c["name"] for c in inspector.get_columns("source_options")]
                if "download_url" not in cols:
                    connection.execute(text("ALTER TABLE source_options ADD COLUMN download_url TEXT"))
                if "status" not in cols:
                    connection.execute(text("ALTER TABLE source_options ADD COLUMN status VARCHAR(50) DEFAULT 'ready' NOT NULL"))
                if "status_reason" not in cols:
                    connection.execute(text("ALTER TABLE source_options ADD COLUMN status_reason TEXT"))
                if "has_audio" not in cols:
                    connection.execute(text("ALTER TABLE source_options ADD COLUMN has_audio BOOLEAN"))
                if "has_video" not in cols:
                    connection.execute(text("ALTER TABLE source_options ADD COLUMN has_video BOOLEAN"))
                if "category" not in cols:
                    connection.execute(text("ALTER TABLE source_options ADD COLUMN category VARCHAR(50) DEFAULT 'recommended'"))
            if "artifacts" in inspector.get_table_names():
                cols = [c["name"] for c in inspector.get_columns("artifacts")]
                if "origin_cache_key" not in cols:
                    connection.execute(text("ALTER TABLE artifacts ADD COLUMN origin_cache_key VARCHAR(128)"))
                if "expires_at" not in cols:
                    connection.execute(text("ALTER TABLE artifacts ADD COLUMN expires_at DATETIME"))
                if "preview_metadata" not in cols:
                    connection.execute(text("ALTER TABLE artifacts ADD COLUMN preview_metadata JSON"))
        await conn.run_sync(_check_and_add_columns)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for obtaining async database sessions."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
