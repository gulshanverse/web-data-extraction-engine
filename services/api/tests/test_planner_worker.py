from __future__ import annotations

import uuid

import pytest
from arq import Retry
from planner_fixtures import options, valid_plan
from sqlalchemy import select
from wde_api.config import Settings
from wde_api.database import SessionFactory
from wde_api.models import ExtractionJob, ExtractionPlan, User, WorkOutbox
from wde_api.planner_errors import PlannerTimeout
from wde_api.planner_model import DeterministicPlannerModel
from wde_api.planner_service import PlannerService
from wde_api.schemas import JobCreateRequest
from wde_api.services import JobService
from wde_api.worker import run_planning

PROJECT_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


async def create_command() -> dict[str, object]:
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
                        "task": "Extract product names and prices from the product catalogue.",
                        "fields": ["name", "price"],
                        "options": options(),
                        "output_formats": ["json"],
                    }
                ),
                principal_id=principal.id,
                idempotency_key=f"worker-{uuid.uuid4()}",
                correlation_id=uuid.uuid4(),
            )
            command = await session.scalar(
                select(WorkOutbox).where(
                    WorkOutbox.job_id == accepted.job_id, WorkOutbox.command_type == "run_planning"
                )
            )
    return command.payload


@pytest.mark.asyncio
async def test_worker_persists_plan_then_exposes_safe_metadata_only() -> None:
    command = await create_command()
    context = {
        "planner_service": PlannerService(
            DeterministicPlannerModel(valid_plan()),
            Settings(planner_max_pages=100, planner_max_records=10_000),
        )
    }
    await run_planning(context, command)
    service = JobService()
    async with SessionFactory() as session:
        plan = await session.scalar(
            select(ExtractionPlan).where(ExtractionPlan.job_id == uuid.UUID(str(command["job_id"])))
        )
        job = await session.get(ExtractionJob, uuid.UUID(str(command["job_id"])))
        projection = await service.status(
            session,
            job_id=job.id,
            principal_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        )
    assert plan and plan.plan["source"]["url"] == "https://example.com/products"
    assert job.status == "BROWSER_INITIALIZING"
    assert projection.plan and projection.plan.plan_hash == plan.plan_hash
    assert projection.plan.model_dump().keys() == {
        "version",
        "status",
        "schema_version",
        "model_name",
        "plan_hash",
        "created_at",
    }


@pytest.mark.asyncio
async def test_worker_raises_retry_only_for_transient_planner_failures() -> None:
    command = await create_command()
    context = {
        "planner_service": PlannerService(
            DeterministicPlannerModel(PlannerTimeout("fixture timeout")),
            Settings(planner_max_retries=2),
        )
    }
    with pytest.raises(Retry):
        await run_planning(context, command)
    async with SessionFactory() as session:
        job = await session.get(ExtractionJob, uuid.UUID(str(command["job_id"])))
    assert job.status == "PLANNING"
    assert job.last_error_code == "PLANNER_TIMEOUT" and job.retryable and job.attempt == 1
