from __future__ import annotations

import uuid

import pytest
from planner_fixtures import options, valid_plan
from sqlalchemy import func, select
from wde_api.browser_types import BrowserOperationResult, NavigationMetadata, NavigationSignalResult
from wde_api.config import Settings
from wde_api.database import SessionFactory
from wde_api.discovery_errors import DiscoveryPolicyBlocked, DiscoveryTimeout
from wde_api.discovery_service import DiscoveryService
from wde_api.models import ExtractionJob, Page, ProgressEvent, Record, User, WorkOutbox
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


async def prepared_discovery_job() -> tuple[JobService, dict[str, object]]:
    service = JobService()
    planner = PlannerService(DeterministicPlannerModel(valid_plan()), Settings())
    async with SessionFactory() as session:
        async with session.begin():
            principal = await session.scalar(select(User).where(User.email == "developer@example.invalid"))
            accepted = await service.create_job(
                session,
                command(),
                principal_id=principal.id,
                idempotency_key=f"discovery-{uuid.uuid4()}",
                correlation_id=uuid.uuid4(),
            )
            planning = await session.scalar(select(WorkOutbox).where(WorkOutbox.job_id == accepted.job_id))
        async with session.begin():
            operation = await service.claim_planning(
                session, planning.payload, worker_id="test", lease_seconds=120
            )
        plan = await planner.create_plan(
            source_url=operation.source_url,
            task=operation.task,
            requested_fields=operation.requested_fields,
            options=operation.options,
            outputs=operation.output_formats,
        )
        async with session.begin():
            await service.complete_planning(
                session,
                planning.payload,
                plan,
                provider_name=planner.model.provider_name,
                model_name=planner.model.model_name,
            )
        async with session.begin():
            browser = await session.scalar(
                select(WorkOutbox).where(
                    WorkOutbox.job_id == accepted.job_id, WorkOutbox.command_type == "run_browser_capture"
                )
            )
        async with session.begin():
            await service.prepare_browser_capture(session, browser.payload, worker_id="test")
        async with session.begin():
            await service.complete_browser_capture(
                session,
                browser.payload,
                BrowserOperationResult(
                    NavigationMetadata(
                        requested_url="https://example.com/products",
                        final_url="https://example.com/products",
                        status=200,
                        content_type="text/html",
                        title="Products",
                        viewport={"width": 1, "height": 1},
                        redirect_count=0,
                        navigation_time_ms=1,
                    )
                ),
            )
        async with session.begin():
            discovery = await session.scalar(
                select(WorkOutbox).where(
                    WorkOutbox.job_id == accepted.job_id, WorkOutbox.command_type == "run_discovery"
                )
            )
    return service, discovery.payload


@pytest.mark.asyncio
async def test_discovery_persists_inventory_events_and_never_creates_records() -> None:
    service, command_payload = await prepared_discovery_job()
    discovery = DiscoveryService(Settings(discovery_max_pages=5, discovery_max_depth=2))
    async with SessionFactory() as session:
        async with session.begin():
            operation = await service.claim_discovery(
                session, command_payload, worker_id="test", lease_seconds=120
            )
        async with session.begin():
            await service.complete_discovery_page(
                session,
                command_payload,
                operation,
                BrowserOperationResult(
                    NavigationMetadata(
                        requested_url=operation.page_url,
                        final_url=operation.page_url,
                        status=200,
                        content_type="text/html",
                        title="Products",
                        viewport={"width": 1, "height": 1},
                        redirect_count=0,
                        navigation_time_ms=1,
                    ),
                    navigation_signals=(
                        NavigationSignalResult("https://example.com/products?page=2", "Next", "next", ""),
                        NavigationSignalResult("/products/item/1", "Product one", "", ""),
                        NavigationSignalResult("https://outside.example/no", "Outside", "", ""),
                    ),
                ),
                discovery=discovery,
            )
        pages = (await session.scalars(select(Page).where(Page.job_id == operation.job_id))).all()
        events = (
            await session.scalars(select(ProgressEvent).where(ProgressEvent.job_id == operation.job_id))
        ).all()
        records = await session.scalar(
            select(func.count()).select_from(Record).where(Record.job_id == operation.job_id)
        )
        job = await session.get(ExtractionJob, operation.job_id)
    assert job.status == "DISCOVERING"
    assert {page.status for page in pages} >= {"VISITED", "DISCOVERED", "REJECTED"}
    assert any(page.discovered_via == "pagination" for page in pages)
    assert any(event.event_type == "page_visited" for event in events)
    assert records == 0


@pytest.mark.asyncio
async def test_discovery_retry_policy_and_cancellation_are_durable() -> None:
    service, command_payload = await prepared_discovery_job()
    async with SessionFactory() as session:
        async with session.begin():
            operation = await service.claim_discovery(
                session, command_payload, worker_id="test", lease_seconds=120
            )
            retry = await service.fail_discovery(
                session, command_payload, DiscoveryTimeout("slow"), max_attempts=2
            )
        assert retry == 1
        async with session.begin():
            operation = await service.claim_discovery(
                session, command_payload, worker_id="test", lease_seconds=120
            )
            job = await session.get(ExtractionJob, operation.job_id)
            job.cancel_requested_at = __import__("datetime").datetime.now(__import__("datetime").UTC)
            no_retry = await service.fail_discovery(
                session, command_payload, DiscoveryPolicyBlocked("blocked"), max_attempts=2
            )
        cancelled = await session.get(ExtractionJob, operation.job_id)
    assert no_retry is None and cancelled.status == "CANCELLED"
