from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    SECRET_KEY: str = "aae-super-secret-dev-key-change-in-prod-1234567890"

    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000
    API_BASE_URL: str = "http://127.0.0.1:8000"
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    MCP_HOST: str = "127.0.0.1"
    MCP_PORT: int = 8001

    DATABASE_URL: str = "sqlite+aiosqlite:///./storage/aae.db"

    STORAGE_BACKEND: str = "local"
    LOCAL_STORAGE_DIR: str = "./storage/artifacts"
    TEMP_STORAGE_DIR: str = "./storage/temp"

    MAX_FILE_SIZE_BYTES: int = 524_288_000  # 500 MB
    DEFAULT_DOWNLOAD_TIMEOUT_SECONDS: int = 300
    EXPIRING_URL_TTL_SECONDS: int = 3600
    ENABLE_SSRF_PROTECTION: bool = True

    WORKER_CONCURRENCY: int = 4
    WORKER_POLL_INTERVAL_SECONDS: float = 0.5
    MAX_RETRIES_PER_JOB: int = 3
    RETRY_BACKOFF_FACTOR: float = 2.0

settings = Settings()
