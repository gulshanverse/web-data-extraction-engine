import uuid

import pytest
from planner_fixtures import valid_plan
from sqlalchemy import select
from wde_api.browser_errors import BrowserCancelled, BrowserLaunchError
from wde_api.browser_types import BrowserArtifactResult, BrowserOperationResult, NavigationMetadata
from wde_api.config import Settings
from wde_api.database import SessionFactory
from wde_api.models import BrowserArtifact, ExtractionJob, ProgressEvent, User, WorkOutbox
from wde_api.planner_model import DeterministicPlannerModel
from wde_api.planner_service import PlannerService
from wde_api.schemas import JobCreateRequest
from wde_api.services import JobService
from wde_api.storage import ArtifactRef

PROJECT_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


def command() -> JobCreateRequest:
    return JobCreateRequest.model_validate(
        {
            "project_id": str(PROJECT_ID),
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
    )


async def prepare_browser_command() -> tuple[JobService, dict[str, object]]:
    service = JobService()
    planner = PlannerService(
        DeterministicPlannerModel(valid_plan()), Settings(planner_max_pages=100, planner_max_records=10_000)
    )
    async with SessionFactory() as session:
        async with session.begin():
            principal = await session.scalar(select(User).where(User.email == "developer@example.invalid"))
            accepted = await service.create_job(
                session,
                command(),
                principal_id=principal.id,
                idempotency_key=f"phase3-orchestration-{uuid.uuid4()}",
                correlation_id=uuid.uuid4(),
            )
            planning = await session.scalar(select(WorkOutbox).where(WorkOutbox.job_id == accepted.job_id))
        async with session.begin():
            operation = await service.claim_planning(
                session, planning.payload, worker_id="test-worker", lease_seconds=120
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
            browser_command = await session.scalar(
                select(WorkOutbox).where(
                    WorkOutbox.job_id == accepted.job_id, WorkOutbox.command_type == "run_browser_capture"
                )
            )
    return service, browser_command.payload


@pytest.mark.asyncio
async def test_persists_browser_navigation_metadata_artifacts_and_events() -> None:
    service, browser_command = await prepare_browser_command()
    artifact = ArtifactRef(
        key="opaque-browser-screenshot",
        artifact_type="browser_screenshot",
        media_type="image/png",
        byte_size=10,
        checksum="sha256:fixture",
        created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        expires_at=None,
    )
    result = BrowserOperationResult(
        NavigationMetadata(
            requested_url="https://example.com/products",
            final_url="https://example.com/products",
            status=200,
            content_type="text/html",
            title="Fixture products",
            viewport={"width": 1440, "height": 900},
            redirect_count=0,
            navigation_time_ms=12,
        ),
        (BrowserArtifactResult("viewport_screenshot", artifact),),
        ({"type": "browser_launched"}, {"type": "navigation_completed"}),
    )
    async with SessionFactory() as session:
        async with session.begin():
            prepared = await service.prepare_browser_capture(
                session, browser_command, worker_id="browser-worker"
            )
            assert prepared and prepared.allowed_domain == "example.com"
        async with session.begin():
            await service.complete_browser_capture(session, browser_command, result)
        page = await session.scalar(
            select(ExtractionJob).where(ExtractionJob.id == uuid.UUID(str(browser_command["job_id"])))
        )
        artifacts = (
            await session.scalars(select(BrowserArtifact).where(BrowserArtifact.job_id == page.id))
        ).all()
        events = (await session.scalars(select(ProgressEvent).where(ProgressEvent.job_id == page.id))).all()
    assert page.status == "BROWSER_INITIALIZING"
    assert page.pages_processed == 1
    assert len(artifacts) == 1 and artifacts[0].storage_key == "opaque-browser-screenshot"
    assert any(event.event_type == "browser_completed" for event in events)


@pytest.mark.asyncio
async def test_browser_cancellation_and_retry_classification_reuse_existing_lifecycle() -> None:
    service, browser_command = await prepare_browser_command()
    async with SessionFactory() as session:
        async with session.begin():
            await service.prepare_browser_capture(session, browser_command, worker_id="browser-worker")
        async with session.begin():
            retry = await service.fail_browser_capture(
                session, browser_command, BrowserLaunchError("Fixture launch failure.")
            )
        job = await session.get(ExtractionJob, uuid.UUID(str(browser_command["job_id"])))
        assert retry and job.status == "BROWSER_INITIALIZING" and job.retryable
    service, browser_command = await prepare_browser_command()
    async with SessionFactory() as session:
        async with session.begin():
            await service.prepare_browser_capture(session, browser_command, worker_id="browser-worker")
        async with session.begin():
            retry = await service.fail_browser_capture(
                session, browser_command, BrowserCancelled("Fixture cancellation.")
            )
        job = await session.get(ExtractionJob, uuid.UUID(str(browser_command["job_id"])))
    assert not retry and job.status == "CANCELLED"
