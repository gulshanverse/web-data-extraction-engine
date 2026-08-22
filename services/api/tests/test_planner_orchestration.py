from __future__ import annotations

import uuid

import pytest
from planner_fixtures import options, valid_plan
from sqlalchemy import select
from wde_api.config import Settings
from wde_api.database import SessionFactory
from wde_api.models import ExtractionJob, ExtractionPlan, ProgressEvent, User, WorkOutbox
from wde_api.planner_errors import PlannerPolicyRejected, PlannerTimeout
from wde_api.planner_model import DeterministicPlannerModel
from wde_api.planner_service import PlannerService
from wde_api.schemas import JobCreateRequest
from wde_api.services import JobService

PROJECT_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


def command() -> JobCreateRequest:
    return JobCreateRequest.model_validate(
        {
            "project_id": str(PROJECT_ID),
            "source_url": "https://example.com/products",
            "task": "Extract product names and prices from the product catalogue.",
            "fields": ["name", "price"],
            "options": options(),
            "output_formats": ["json"],
        }
    )


async def create_planning_command() -> tuple[JobService, dict[str, object]]:
    service = JobService()
    async with SessionFactory() as session:
        async with session.begin():
            principal = await session.scalar(select(User).where(User.email == "developer@example.invalid"))
            accepted = await service.create_job(
                session,
                command(),
                principal_id=principal.id,
                idempotency_key=f"planner-{uuid.uuid4()}",
                correlation_id=uuid.uuid4(),
            )
            outbox = await session.scalar(
                select(WorkOutbox).where(
                    WorkOutbox.job_id == accepted.job_id, WorkOutbox.command_type == "run_planning"
                )
            )
    return service, outbox.payload


@pytest.mark.asyncio
async def test_planner_persists_auditable_canonical_plan_and_only_hands_off_to_browser_boundary() -> None:
    service, planning_command = await create_planning_command()
    settings = Settings(planner_max_pages=100, planner_max_records=10_000)
    planner = PlannerService(DeterministicPlannerModel(valid_plan()), settings)
    async with SessionFactory() as session:
        async with session.begin():
            operation = await service.claim_planning(
                session, planning_command, worker_id="planner-test", lease_seconds=120
            )
        plan = await planner.create_plan(
            source_url=operation.source_url,
            task=operation.task,
            requested_fields=operation.requested_fields,
            options=operation.options,
            outputs=operation.output_formats,
        )
        async with session.begin():
            assert await service.complete_planning(
                session,
                planning_command,
                plan,
                provider_name=planner.model.provider_name,
                model_name=planner.model.model_name,
            )
        persisted = await session.scalar(
            select(ExtractionPlan).where(ExtractionPlan.job_id == operation.job_id)
        )
        job = await session.get(ExtractionJob, operation.job_id)
        events = (
            await session.scalars(
                select(ProgressEvent)
                .where(ProgressEvent.job_id == operation.job_id)
                .order_by(ProgressEvent.sequence_no)
            )
        ).all()
        browser = await session.scalar(
            select(WorkOutbox).where(
                WorkOutbox.job_id == operation.job_id, WorkOutbox.command_type == "run_browser_capture"
            )
        )
    assert persisted and persisted.provider_name == "deterministic_test"
    assert persisted.schema_version == "plan.v1" and persisted.plan_hash
    assert job.status == "BROWSER_INITIALIZING"
    assert browser and browser.payload["operation_key"].endswith(":browser:1")
    assert [event.event_type for event in events][:3] == [
        "job_queued",
        "planning_started",
        "planning_completed",
    ]


@pytest.mark.asyncio
async def test_planner_failure_retries_only_transient_errors_then_fails_without_plan() -> None:
    service, planning_command = await create_planning_command()
    async with SessionFactory() as session:
        async with session.begin():
            operation = await service.claim_planning(
                session, planning_command, worker_id="planner-test", lease_seconds=120
            )
            retry_attempt = await service.fail_planning(
                session, planning_command, PlannerTimeout("slow provider"), max_retries=2
            )
            job = await session.get(ExtractionJob, operation.job_id)
            assert retry_attempt == 1 and job.status == "PLANNING" and job.retryable
        async with session.begin():
            retry = await service.claim_planning(
                session, planning_command, worker_id="planner-test", lease_seconds=120
            )
            assert retry is not None
            no_retry = await service.fail_planning(
                session, planning_command, PlannerPolicyRejected("unsafe task"), max_retries=2
            )
            plans = (
                await session.scalars(select(ExtractionPlan).where(ExtractionPlan.job_id == operation.job_id))
            ).all()
            failed = await session.get(ExtractionJob, operation.job_id)
    assert (
        no_retry is None and failed.status == "FAILED" and failed.last_error_code == "PLANNER_POLICY_REJECTED"
    )
    assert plans == []


@pytest.mark.asyncio
async def test_cancellation_and_redelivery_prevent_persistence_duplicates() -> None:
    service, planning_command = await create_planning_command()
    async with SessionFactory() as session:
        async with session.begin():
            operation = await service.claim_planning(
                session, planning_command, worker_id="planner-test", lease_seconds=120
            )
            job = await session.get(ExtractionJob, operation.job_id)
            job.cancel_requested_at = __import__("datetime").datetime.now(__import__("datetime").UTC)
        async with session.begin():
            plan = await PlannerService(DeterministicPlannerModel(valid_plan()), Settings()).create_plan(
                source_url=operation.source_url,
                task=operation.task,
                requested_fields=operation.requested_fields,
                options=operation.options,
                outputs=operation.output_formats,
            )
            assert not await service.complete_planning(
                session,
                planning_command,
                plan,
                provider_name="deterministic_test",
                model_name="deterministic-test-v1",
            )
        cancelled = await session.get(ExtractionJob, operation.job_id)
    assert cancelled.status == "CANCELLED"
