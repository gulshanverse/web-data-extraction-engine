from __future__ import annotations

import uuid

import pytest
from planner_fixtures import options, valid_plan
from sqlalchemy import func, select
from wde_api.database import SessionFactory
from wde_api.extraction_errors import ExtractionTimeout
from wde_api.extraction_service import ExtractionService
from wde_api.extraction_types import ExtractionDocument, TableSignal
from wde_api.models import ExtractionJob, ExtractionPlan, Page, Record, User
from wde_api.schemas import JobCreateRequest
from wde_api.services import JobService

PROJECT_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


async def extraction_ready() -> tuple[JobService, dict[str, object], object]:
    service = JobService()
    async with SessionFactory() as session:
        async with session.begin():
            principal = await session.scalar(select(User).where(User.email == "developer@example.invalid"))
            accepted = await service.create_job(
                session,
                JobCreateRequest.model_validate(
                    {
                        "project_id": str(PROJECT_ID),
                        "source_url": "https://example.com/products",
                        "task": "Extract products",
                        "fields": ["name", "price"],
                        "options": options(),
                        "output_formats": ["json"],
                    }
                ),
                principal_id=principal.id,
                idempotency_key=f"extract-{uuid.uuid4()}",
                correlation_id=uuid.uuid4(),
            )
            job = await session.get(ExtractionJob, accepted.job_id)
            job.status = "EXTRACTING"
            plan_row = ExtractionPlan(
                job_id=job.id, version=1, status="DRAFT", plan=valid_plan(), model_name="test"
            )
            session.add(plan_row)
            page = Page(
                job_id=job.id,
                url="https://example.com/products",
                canonical_url="https://example.com/products",
                status="VISITED",
                depth=0,
            )
            session.add(page)
            await session.flush()
            command = {
                "job_id": str(job.id),
                "project_id": str(job.project_id),
                "correlation_id": str(job.correlation_id),
                "operation_key": f"job:{job.id}:extraction:1",
                "page_id": str(page.id),
                "attempt": 1,
            }
    return service, command, page.id


@pytest.mark.asyncio
async def test_extraction_persists_records_idempotently_and_stops_at_validation_boundary() -> None:
    service, command, page_id = await extraction_ready()
    async with SessionFactory() as session:
        async with session.begin():
            operation = await service.claim_extraction(session, command, worker_id="test", lease_seconds=120)
        result = ExtractionService().extract(
            plan=operation.plan,
            page_url=operation.page_url,
            page_id=str(operation.page_id),
            document=ExtractionDocument(tables=(TableSignal(("name", "price"), (("A", "$1"),)),)),
        )
        async with session.begin():
            await service.complete_extraction_page(session, command, operation, result)
        records = (await session.scalars(select(Record).where(Record.job_id == operation.job_id))).all()
        job = await session.get(ExtractionJob, operation.job_id)
        page = await session.get(Page, page_id)
        validation_count = await session.scalar(
            select(func.count())
            .select_from(__import__("wde_api.models", fromlist=["ValidationResult"]).ValidationResult)
            .where(
                __import__("wde_api.models", fromlist=["ValidationResult"]).ValidationResult.job_id
                == operation.job_id
            )
        )
    assert job.status == "VALIDATING" and page.extraction_status == "EXTRACTED"
    assert len(records) == 1 and records[0].plan_version == 1 and records[0].record_identity
    assert validation_count == 0


@pytest.mark.asyncio
async def test_extraction_retry_and_cancellation_are_durable() -> None:
    service, command, _ = await extraction_ready()
    async with SessionFactory() as session:
        async with session.begin():
            operation = await service.claim_extraction(session, command, worker_id="test", lease_seconds=120)
            retry = await service.fail_extraction(session, command, ExtractionTimeout("slow"), max_attempts=2)
        assert retry == 1
        async with session.begin():
            operation = await service.claim_extraction(session, command, worker_id="test", lease_seconds=120)
            job = await session.get(ExtractionJob, operation.job_id)
            job.cancel_requested_at = __import__("datetime").datetime.now(__import__("datetime").UTC)
            no_retry = await service.fail_extraction(
                session, command, ExtractionTimeout("slow"), max_attempts=2
            )
        job = await session.get(ExtractionJob, operation.job_id)
    assert no_retry is None and job.status == "CANCELLED"
