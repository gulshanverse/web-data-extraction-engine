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
    browser_headless: bool = True
    browser_navigation_timeout_ms: int = Field(default=30_000, ge=1_000, le=120_000)
    browser_action_timeout_ms: int = Field(default=10_000, ge=500, le=60_000)
    browser_page_timeout_ms: int = Field(default=45_000, ge=1_000, le=180_000)
    browser_launch_timeout_ms: int = Field(default=30_000, ge=1_000, le=120_000)
    browser_shutdown_timeout_ms: int = Field(default=10_000, ge=1_000, le=60_000)
    browser_max_pages: int = Field(default=1, ge=1, le=20)
    browser_max_redirects: int = Field(default=5, ge=0, le=20)
    browser_max_contexts: int = Field(default=2, ge=1, le=16)
    browser_max_lifetime_seconds: int = Field(default=120, ge=5, le=900)
    browser_max_response_bytes: int = Field(default=10_485_760, ge=65_536, le=104_857_600)
    browser_max_screenshot_bytes: int = Field(default=5_242_880, ge=65_536, le=20_971_520)
    browser_max_download_bytes: int = Field(default=10_485_760, ge=65_536, le=104_857_600)
    browser_viewport_width: int = Field(default=1440, ge=320, le=3840)
    browser_viewport_height: int = Field(default=900, ge=320, le=2160)
    browser_locale: str = "en-US"
    browser_timezone_id: str = "UTC"
    browser_user_agent: str = (
        "WebDataExtractionEngine/0.3 (+https://github.com/gulshanverse/web-data-extraction-engine)"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
