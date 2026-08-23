from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration. Production is deliberately fail-closed."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"
    app_url: str = ""
    api_url: str = ""
    database_url: str = "postgresql+asyncpg://wde:wde@localhost:5432/wde"
    database_pool_size: int = Field(default=5, ge=1, le=20)
    database_max_overflow: int = Field(default=2, ge=0, le=10)
    database_pool_timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)
    redis_url: str = "redis://localhost:6379/0"
    redis_operation_budget_per_minute: int = Field(default=3000, ge=100, le=100_000)
    artifact_root: Path = Path("/tmp/web-data-extraction-engine-artifacts")
    storage_provider: Literal["local", "supabase"] = "local"
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = ""
    supabase_jwt_audience: str = "authenticated"
    supabase_jwks_cache_seconds: int = Field(default=300, ge=1, le=600)
    supabase_request_timeout_seconds: float = Field(default=15.0, ge=1.0, le=60.0)
    app_session_secret: str = ""
    auth_session_max_age_seconds: int = Field(default=900, ge=60, le=3600)
    cors_allowed_origins: str = ""
    trusted_hosts: str = ""
    artifact_retention_days: int = Field(default=14, ge=1, le=365)
    artifact_cleanup_batch_size: int = Field(default=100, ge=1, le=1000)
    max_concurrent_jobs: int = Field(default=2, ge=1, le=8)
    max_request_bytes: int = Field(default=1_048_576, ge=1_024, le=10_485_760)
    api_rate_limit_requests: int = Field(default=120, ge=10, le=10_000)
    api_rate_limit_window_seconds: float = Field(default=60.0, ge=1.0, le=3600.0)
    dev_principal_email: str = "developer@example.invalid"
    worker_lease_seconds: int = Field(default=120, ge=30, le=3600)
    api_event_poll_seconds: float = Field(default=0.5, ge=0.1, le=5.0)
    browser_headless: bool = True
    browser_navigation_timeout_ms: int = Field(default=30_000, ge=1_000, le=120_000)
    browser_action_timeout_ms: int = Field(default=10_000, ge=500, le=60_000)
    browser_page_timeout_ms: int = Field(default=45_000, ge=1_000, le=180_000)
    browser_launch_timeout_ms: int = Field(default=30_000, ge=1_000, le=120_000)
    browser_shutdown_timeout_ms: int = Field(default=10_000, ge=1_000, le=60_000)
    browser_max_concurrency: int = Field(default=1, ge=1, le=4)
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
    browser_user_agent: str = "WebDataExtractionEngine/0.3 (+https://github.com/gulshanverse/web-data-extraction-engine)"
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
    extraction_max_records: int = Field(default=10_000, ge=1, le=100_000)
    extraction_max_evidence_chars: int = Field(default=500, ge=64, le=4_000)
    extraction_max_document_chars: int = Field(default=200_000, ge=1_024, le=2_000_000)
    extraction_max_document_items: int = Field(default=500, ge=1, le=5_000)
    extraction_max_retries: int = Field(default=2, ge=0, le=5)
    export_max_records: int = Field(default=10_000, ge=1, le=100_000)
    export_max_bytes: int = Field(default=25_165_824, ge=65_536, le=52_428_800)
    export_timeout_seconds: float = Field(default=60.0, ge=1.0, le=300.0)
    export_max_concurrency: int = Field(default=2, ge=1, le=8)
    export_max_retries: int = Field(default=2, ge=0, le=5)

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip().rstrip("/") for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        return [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]

    @property
    def supabase_jwks_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @model_validator(mode="after")
    def validate_production_topology(self) -> Settings:
        if self.app_env != "production":
            return self
        required = {
            "APP_URL": self.app_url,
            "API_URL": self.api_url,
            "SUPABASE_URL": self.supabase_url,
            "SUPABASE_ANON_KEY": self.supabase_anon_key,
            "SUPABASE_SERVICE_ROLE_KEY": self.supabase_service_role_key,
            "SUPABASE_STORAGE_BUCKET": self.supabase_storage_bucket,
            "APP_SESSION_SECRET": self.app_session_secret,
            "CORS_ALLOWED_ORIGINS": self.cors_allowed_origins,
            "TRUSTED_HOSTS": self.trusted_hosts,
        }
        missing = [name for name, value in required.items() if not value or "replace-with" in value.lower()]
        if missing:
            raise ValueError(f"Production settings missing required values: {', '.join(missing)}")
        for name, value in {"APP_URL": self.app_url, "API_URL": self.api_url, "SUPABASE_URL": self.supabase_url}.items():
            if urlparse(value).scheme != "https" or not urlparse(value).hostname:
                raise ValueError(f"{name} must be an HTTPS URL in production.")
        if self.storage_provider != "supabase":
            raise ValueError("Production requires STORAGE_PROVIDER=supabase.")
        if not self.database_url.startswith("postgresql+asyncpg://") or "localhost" in self.database_url:
            raise ValueError("Production DATABASE_URL must use the managed async PostgreSQL endpoint.")
        if "ssl=" not in self.database_url and "sslmode=" not in self.database_url:
            raise ValueError("Production DATABASE_URL must require TLS.")
        if not self.redis_url.startswith("rediss://"):
            raise ValueError("Production REDIS_URL must use rediss:// TLS.")
        if not self.cors_origins or any(origin == "*" or urlparse(origin).scheme != "https" for origin in self.cors_origins):
            raise ValueError("Production CORS_ALLOWED_ORIGINS must contain explicit HTTPS origins.")
        if not self.trusted_host_list or "*" in self.trusted_host_list:
            raise ValueError("Production TRUSTED_HOSTS must contain explicit hosts.")
        if self.export_max_bytes > 52_428_800:
            raise ValueError("EXPORT_MAX_BYTES exceeds the Supabase Free storage file ceiling.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
