import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest
from fastapi.testclient import TestClient
from wde_api.main import app

PROJECT_ID = "22222222-2222-2222-2222-222222222222"


def payload(**overrides: object) -> dict[str, object]:
    request: dict[str, object] = {
        "project_id": PROJECT_ID,
        "source_url": "https://example.com/products",
        "task": "Extract product names, prices, and canonical product URLs.",
        "fields": ["name", "price", "url"],
        "options": {
            "max_pages": 20,
            "max_records": 1000,
            "follow_pagination": True,
            "follow_relevant_links": False,
            "extract_images": False,
            "deduplicate": True,
            "validate": True,
        },
        "output_formats": ["json"],
    }
    request.update(overrides)
    return request


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_health_and_openapi_are_exposed(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    schema = client.get("/openapi.json").json()
    assert "/api/jobs" in schema["paths"]
    assert "/api/jobs/{job_id}/events" in schema["paths"]


def test_rejects_malformed_and_internal_urls(client: TestClient) -> None:
    malformed = client.post("/api/jobs", json=payload(source_url="not-a-url"))
    internal = client.post("/api/jobs", json=payload(source_url="http://127.0.0.1"))
    assert malformed.status_code in {400, 422}
    assert malformed.json()["error"]["code"] in {"INVALID_URL", "INVALID_REQUEST"}
    assert internal.status_code == 403
    assert internal.json()["error"]["code"] == "DOMAIN_NOT_ALLOWED"


def test_rejects_unsupported_format_and_resource_limit(client: TestClient) -> None:
    unsupported = client.post("/api/jobs", json=payload(output_formats=["exe"]))
    oversized = client.post("/api/jobs", json=payload(options={**payload()["options"], "max_pages": 101}))
    assert unsupported.status_code == 422
    assert unsupported.json()["error"]["code"] == "UNSUPPORTED_FORMAT"
    assert oversized.status_code == 422
    assert oversized.json()["error"]["code"] == "RESOURCE_LIMIT_EXCEEDED"


def test_missing_job_uses_safe_not_found_error(client: TestClient) -> None:
    response = client.get(f"/api/jobs/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_rejects_project_without_development_principal_ownership(client: TestClient) -> None:
    response = client.post("/api/jobs", json=payload(project_id="33333333-3333-3333-3333-333333333333"))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_AUTHORIZED"


def test_creates_a_durable_job_and_replays_same_idempotency_key(client: TestClient) -> None:
    headers = {"Idempotency-Key": "test-replay-key"}
    first = client.post("/api/jobs", json=payload(), headers=headers)
    second = client.post("/api/jobs", json=payload(), headers=headers)
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]
    assert first.json()["status"] == "QUEUED"


def test_rejects_conflicting_idempotency_payload(client: TestClient) -> None:
    headers = {"Idempotency-Key": "test-conflict-key"}
    assert client.post("/api/jobs", json=payload(), headers=headers).status_code == 202
    conflict = client.post(
        "/api/jobs",
        json=payload(task="Extract different product fields from the same permitted source."),
        headers=headers,
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_concurrent_duplicate_requests_create_one_durable_job() -> None:
    headers = {"Idempotency-Key": "test-concurrent-key"}

    def submit() -> tuple[int, str]:
        with TestClient(app, raise_server_exceptions=False) as threaded_client:
            response = threaded_client.post("/api/jobs", json=payload(), headers=headers)
            return response.status_code, response.json()["job_id"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = list(executor.map(lambda _: submit(), range(2)))
    assert first[0] == second[0] == 202
    assert first[1] == second[1]


def test_cancellation_is_durable_idempotent_and_exposes_empty_contracts(client: TestClient) -> None:
    created = client.post("/api/jobs", json=payload(), headers={"Idempotency-Key": "test-cancel-key"})
    job_id = created.json()["job_id"]
    first = client.post(f"/api/jobs/{job_id}/cancel")
    second = client.post(f"/api/jobs/{job_id}/cancel")
    assert first.status_code == second.status_code == 202
    assert first.json()["status"] == second.json()["status"] == "CANCELLED"
    assert client.get(f"/api/jobs/{job_id}/results").json()["items"] == []
    assert client.get(f"/api/jobs/{job_id}/files").json()["files"] == []


def test_completed_job_rejects_cancellation(client: TestClient) -> None:
    if not (database_url := os.environ.get("WDE_TEST_DATABASE_URL")):
        pytest.skip("Requires the isolated integration database.")
    created = client.post(
        "/api/jobs", json=payload(), headers={"Idempotency-Key": "test-completed-cancel-key"}
    )
    job_id = created.json()["job_id"]
    with psycopg.connect(database_url.replace("postgresql+asyncpg", "postgresql")) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE extraction_jobs SET status = 'COMPLETED', completed_at = CURRENT_TIMESTAMP WHERE id = %s",
                (job_id,),
            )
        connection.commit()
    response = client.post(f"/api/jobs/{job_id}/cancel")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"
