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
    planner_provider: str = "openai_compatible"
    planner_model: str = "gpt-5-mini"
    planner_api_endpoint: str = ""
    planner_api_key: str = ""
    planner_timeout_seconds: float = Field(default=30.0, ge=1.0, le=120.0)
    planner_max_retries: int = Field(default=2, ge=0, le=5)
    planner_max_output_tokens: int = Field(default=2048, ge=256, le=8192)
    planner_max_task_chars: int = Field(default=8_000, ge=256, le=32_000)
    planner_max_pages: int = Field(default=100, ge=1, le=1_000)
    planner_max_records: int = Field(default=10_000, ge=1, le=100_000)
    planner_max_fields: int = Field(default=64, ge=1, le=128)
    planner_max_outputs: int = Field(default=7, ge=1, le=7)
    discovery_max_pages: int = Field(default=100, ge=1, le=1_000)
    discovery_max_depth: int = Field(default=2, ge=0, le=10)
    discovery_max_links_per_page: int = Field(default=200, ge=1, le=2_000)
    discovery_max_concurrency: int = Field(default=1, ge=1, le=8)
    discovery_min_delay_seconds: float = Field(default=0.0, ge=0.0, le=10.0)
    discovery_scope_policy: str = "SAME_ORIGIN"
    discovery_enable_sitemaps: bool = False
    discovery_sitemap_max_bytes: int = Field(default=1_048_576, ge=1_024, le=10_485_760)
    discovery_sitemap_max_urls: int = Field(default=500, ge=1, le=10_000)
    discovery_sitemap_max_depth: int = Field(default=1, ge=0, le=5)


@lru_cache
def get_settings() -> Settings:
    return Settings()
