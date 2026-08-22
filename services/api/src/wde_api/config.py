"""Typed environment settings; credentials are supplied only at runtime."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://wde:wde@localhost:5432/wde"
    redis_url: str = "redis://localhost:6379/0"
    artifact_root: Path = Path("/tmp/web-data-extraction-engine-artifacts")
    max_request_bytes: int = Field(default=1_048_576, ge=1_024, le=10_485_760)
    dev_principal_email: str = "developer@example.invalid"
    worker_lease_seconds: int = Field(default=120, ge=30, le=3600)
    api_event_poll_seconds: float = Field(default=0.5, ge=0.1, le=5.0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
