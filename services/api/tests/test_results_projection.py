import uuid

import pytest
from fastapi.testclient import TestClient
from wde_api.database import SessionFactory
from wde_api.main import app
from wde_api.models import ExtractionJob, Project, Record, User, ValidationResult, ValidationRun

PROJECT_ID = "22222222-2222-2222-2222-222222222222"


def job_payload() -> dict[str, object]:
    return {
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


def record_payload(name: str, price: float) -> dict[str, object]:
    return {
        "schema_version": "records.v1",
        "fields": {
            "name": {"raw": name, "value": name, "evidence": {"source_text": "private"}},
            "price": {"raw": str(price), "value": price, "evidence": {"source_text": "private"}},
            "url": {"raw": "https://example.com/item", "value": "https://example.com/item"},
        },
        "provenance": {"source_url": "https://example.com/item"},
    }


async def create_completed_results_job() -> tuple[str, list[uuid.UUID]]:
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/jobs", json=job_payload(), headers={"Idempotency-Key": str(uuid.uuid4())}
        )
    job_id = uuid.UUID(response.json()["job_id"])
    async with SessionFactory() as session:
        async with session.begin():
            job = await session.get(ExtractionJob, job_id)
            assert job is not None
            job.status = "COMPLETED"
            validation_run = ValidationRun(
                job_id=job.id,
                run_number=1,
                operation_key=f"job:{job.id}:validation:run:1",
                status="COMPLETED",
                schema_version="validation.v1",
                ruleset_version="rules.v1",
                plan_version=1,
                summary={"records": 4, "passed": 1, "failed": 1, "warnings": 1, "unresolved": 1},
            )
            session.add(validation_run)
            await session.flush()
            outcomes = [
                ("PASS", "HIGH"),
                ("FAIL", "INVALID"),
                ("WARN", "MEDIUM"),
                ("UNRESOLVED", "UNRESOLVED"),
            ]
            records: list[Record] = []
            for index, (status, quality) in enumerate(outcomes, start=1):
                record = Record(
                    job_id=job.id,
                    payload=record_payload(f"Record {index}", float(index)),
                    record_identity=f"record-{index}",
                    plan_version=1,
                    strategy="table",
                )
                session.add(record)
                records.append(record)
                await session.flush()
                session.add(
                    ValidationResult(
                        job_id=job.id,
                        record_id=record.id,
                        validation_run_id=validation_run.id,
                        status=status,
                        quality=quality,
                        findings={},
                        summary={
                            "pass": int(status == "PASS"),
                            "fail": int(status == "FAIL"),
                            "warn": int(status == "WARN"),
                            "unresolved": int(status == "UNRESOLVED"),
                        },
                    )
                )
        return str(job.id), [record.id for record in records]


@pytest.mark.asyncio
async def test_results_projects_durable_values_validation_metrics_and_pagination() -> None:
    job_id, record_ids = await create_completed_results_job()
    with TestClient(app, raise_server_exceptions=False) as client:
        first = client.get(f"/api/jobs/{job_id}/results?page=1&page_size=2")
        second = client.get(f"/api/jobs/{job_id}/results?page=2&page_size=2")
    assert first.status_code == second.status_code == 200
    payload = first.json()
    assert payload["total"] == 4
    assert payload["validation_available"] is True
    assert payload["validation_summary"] == {
        "records": 4,
        "passed": 1,
        "warnings": 1,
        "failed": 1,
        "unresolved": 1,
    }
    first_ids = {item["record_id"] for item in payload["items"]}
    second_items = second.json()["items"]
    assert first_ids.isdisjoint({item["record_id"] for item in second_items})
    assert first_ids | {item["record_id"] for item in second_items} == {
        str(record_id) for record_id in record_ids
    }
    projected = {item["data"]["name"]: item for item in payload["items"] + second_items}
    assert projected["Record 1"]["data"] == {
        "name": "Record 1",
        "price": 1.0,
        "url": "https://example.com/item",
    }
    assert projected["Record 1"]["validation"] == {
        "status": "PASS",
        "quality": "HIGH",
        "summary": {"pass": 1, "fail": 0, "warn": 0, "unresolved": 0},
    }
    assert {item["validation"]["status"] for item in projected.values()} == {
        "PASS",
        "FAIL",
        "WARN",
        "UNRESOLVED",
    }
    assert "evidence" not in str(projected["Record 1"])
    assert all(item["validation"] != "PENDING" for item in payload["items"])


@pytest.mark.asyncio
async def test_results_explicitly_report_absent_validation_and_enforce_ownership() -> None:
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/jobs", json=job_payload(), headers={"Idempotency-Key": str(uuid.uuid4())}
        )
        job_id = response.json()["job_id"]
    async with SessionFactory() as session:
        async with session.begin():
            job = await session.get(ExtractionJob, uuid.UUID(job_id))
            assert job is not None
            job.status = "COMPLETED"
            session.add(
                Record(
                    job_id=job.id,
                    payload=record_payload("No validation", 9.0),
                    record_identity="no-validation",
                )
            )
            other = User(email="other@example.invalid")
            session.add(other)
            await session.flush()
            session.add(Project(owner_id=other.id, name="Other project"))
    with TestClient(app, raise_server_exceptions=False) as client:
        own = client.get(f"/api/jobs/{job_id}/results")
        denied = client.get(
            f"/api/jobs/{job_id}/results", headers={"X-Dev-Principal": "other@example.invalid"}
        )
    assert own.status_code == 200
    assert own.json()["validation_available"] is False
    assert own.json()["items"][0]["validation"] is None
    assert denied.status_code in {403, 404}
