from wde_api.config import get_settings
from wde_api.queue import redis_settings


def test_redis_settings_preserve_rediss_credentials_and_database(monkeypatch) -> None:
    monkeypatch.setenv("REDIS_URL", "rediss://worker:secret@redis.example.test:6380/7")
    get_settings.cache_clear()
    try:
        settings = redis_settings()
        assert settings.host == "redis.example.test"
        assert settings.port == 6380
        assert settings.database == 7
        assert settings.username == "worker"
        assert settings.password == "secret"
        assert settings.ssl is True
    finally:
        get_settings.cache_clear()
