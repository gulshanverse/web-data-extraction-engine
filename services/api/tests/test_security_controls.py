from fastapi.testclient import TestClient
from wde_api import main
from wde_api.main import app
from wde_api.security import SlidingWindowRateLimiter


def test_sliding_window_limiter_is_bounded_per_client_key() -> None:
    limiter = SlidingWindowRateLimiter(limit=2, window_seconds=60)
    assert limiter.allow("client-a") is True
    assert limiter.allow("client-a") is True
    assert limiter.allow("client-a") is False
    assert limiter.allow("client-b") is True


def test_api_adds_non_cacheable_security_headers() -> None:
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/jobs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-correlation-id"]


def test_api_rejects_declared_oversized_mutation_body() -> None:
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/jobs",
            content=b"{}",
            headers={"Content-Type": "application/json", "Content-Length": "1048577"},
        )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "RESOURCE_LIMIT_EXCEEDED"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"


def test_api_returns_safe_rate_limit_response(monkeypatch) -> None:
    monkeypatch.setattr(main, "rate_limiter", SlidingWindowRateLimiter(limit=1, window_seconds=60))
    with TestClient(app, raise_server_exceptions=False) as client:
        client.get("/api/jobs/00000000-0000-0000-0000-000000000000")
        response = client.get("/api/jobs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"
    assert response.headers["retry-after"]
    assert response.headers["x-content-type-options"] == "nosniff"
