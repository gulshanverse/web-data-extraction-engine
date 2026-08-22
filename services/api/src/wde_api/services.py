"""Application service and orchestrator for durable Phase 2 jobs. Future engines are represented only by a deterministic planning placeholder."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from wde_api.auth import NotAuthorized
from wde_api.browser_errors import BrowserCancelled, BrowserEngineError
from wde_api.browser_types import BrowserOperationRequest, BrowserOperationResult
from wde_api.discovery_errors import DiscoveryError
from wde_api.discovery_service import DiscoveryService
from wde_api.discovery_types import DiscoveryCandidate, DiscoveryMethod, InventoryStatus, NavigationSignal
from wde_api.domain import (
    ACTIVE_STATES,
    EVENT_FOR_TRANSITION,
    InvalidTransition,
    JobStatus,
    assert_transition,
    retry_delay_seconds,
)
from wde_api.extraction_errors import ExtractionError
from wde_api.extraction_types import ExtractionResult
from wde_api.models import (
    BrowserArtifact,
    ExtractionJob,
    ExtractionPlan,
    IdempotencyKey,
    Page,
    ProgressEvent,
    Project,
    Record,
    Source,
    WorkOutbox,
)
from wde_api.planner_errors import PlannerError
from wde_api.planner_types import PROMPT_VERSION, CanonicalPlan, plan_hash
from wde_api.schemas import (
    CancelResponse,
    FilesResponse,
    JobAccepted,
    JobCreateRequest,
    JobStatusResponse,
    PlanProjection,
    ProgressProjection,
    ResultsResponse,
)
from wde_api.url_policy import validate_initial_url


def utcnow() -> datetime:
    return datetime.now(UTC)


def request_fingerprint(command: JobCreateRequest) -> str:
    payload = command.model_dump(mode="json")
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class PlanningOperation:
    job_id: uuid.UUID
    project_id: uuid.UUID
    correlation_id: uuid.UUID
    operation_key: str
    source_url: str
    task: str
    requested_fields: list[str]
    options: dict[str, object]
    output_formats: list[str]


@dataclass(frozen=True)
class DiscoveryOperation:
    job_id: uuid.UUID
    project_id: uuid.UUID
    correlation_id: uuid.UUID
    operation_key: str
    page_id: uuid.UUID
    page_url: str
    page_canonical_url: str
    page_depth: int
    page_method: str | None
    source_domain: str
    plan: CanonicalPlan


@dataclass(frozen=True)
class ExtractionOperation:
    job_id: uuid.UUID
    project_id: uuid.UUID
    correlation_id: uuid.UUID
    operation_key: str
    page_id: uuid.UUID
    page_url: str
    source_domain: str
    plan: CanonicalPlan


class JobService:
    async def assert_project_access(
        self, session: AsyncSession, project_id: uuid.UUID, principal_id: uuid.UUID
    ) -> Project:
        project = await session.scalar(
            select(Project).where(Project.id == project_id, Project.owner_id == principal_id)
        )
        if project is None:
            raise NotAuthorized("You do not have access to this project.")
        return project

    async def get_job(
        self, session: AsyncSession, job_id: uuid.UUID, principal_id: uuid.UUID
    ) -> ExtractionJob:
        job = await session.scalar(
            select(ExtractionJob)
            .join(Project)
            .where(ExtractionJob.id == job_id, Project.owner_id == principal_id)
        )
        if job is None:
            from wde_api.domain import DomainError

            error = DomainError("The requested job was not found.")
            error.code, error.status_code = "NOT_FOUND", 404
            raise error
        return job

    async def create_job(
        self,
        session: AsyncSession,
        command: JobCreateRequest,
        *,
        principal_id: uuid.UUID,
        idempotency_key: str | None,
        correlation_id: uuid.UUID,
    ) -> JobAccepted:
        await self.assert_project_access(session, command.project_id, principal_id)
        fingerprint = request_fingerprint(command)
        if idempotency_key:
            # Serialize only identical project/key commands. The durable unique constraint remains the
            # final guard; this lock makes concurrent safe retries observe the committed original row.
            await session.execute(
                select(func.pg_advisory_xact_lock(func.hashtext(f"{command.project_id}:{idempotency_key}")))
            )
            existing = await session.scalar(
                select(IdempotencyKey).where(
                    IdempotencyKey.project_id == command.project_id, IdempotencyKey.key == idempotency_key
                )
            )
            if existing:
                if existing.request_hash != fingerprint:
                    from wde_api.domain import DomainError

                    error = DomainError("This idempotency key was already used with a different request.")
                    error.code, error.status_code = "IDEMPOTENCY_CONFLICT", 409
                    raise error
                job = await session.get(ExtractionJob, existing.job_id)
                return self.accepted(job)
        canonical = validate_initial_url(command.source_url)
        source = await session.scalar(
            select(Source).where(
                Source.project_id == command.project_id, Source.canonical_url == canonical.canonical_url
            )
        )
        if source is None:
            source = Source(
                project_id=command.project_id, canonical_url=canonical.canonical_url, domain=canonical.domain
            )
            session.add(source)
            await session.flush()
        job = ExtractionJob(
            project_id=command.project_id,
            source_id=source.id,
            task_description=command.task,
            requested_fields=command.fields,
            options=command.options.model_dump(by_alias=True),
            output_formats=command.output_formats,
            correlation_id=correlation_id,
        )
        session.add(job)
        await session.flush()
        await self._append_event(
            session,
            job,
            "job_queued",
            {"stage": JobStatus.QUEUED.value, "percent": 0, "message": "Job accepted"},
            correlation_id,
        )
        operation_key = f"job:{job.id}:planning:1"
        session.add(
            WorkOutbox(
                job_id=job.id,
                project_id=job.project_id,
                command_type="run_planning",
                operation_key=operation_key,
                payload={
                    "job_id": str(job.id),
                    "project_id": str(job.project_id),
                    "correlation_id": str(correlation_id),
                    "operation_key": operation_key,
                    "attempt": 1,
                },
            )
        )
        if idempotency_key:
            session.add(
                IdempotencyKey(
                    project_id=job.project_id, key=idempotency_key, request_hash=fingerprint, job_id=job.id
                )
            )
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            if not idempotency_key:
                raise
            existing = await session.scalar(
                select(IdempotencyKey).where(
                    IdempotencyKey.project_id == command.project_id, IdempotencyKey.key == idempotency_key
                )
            )
            if existing and existing.request_hash == fingerprint:
                existing_job = await session.get(ExtractionJob, existing.job_id)
                return self.accepted(existing_job)
            raise
        return self.accepted(job)

    def accepted(self, job: ExtractionJob) -> JobAccepted:
        return JobAccepted(
            job_id=job.id,
            project_id=job.project_id,
            status=job.status,
            progress=ProgressProjection(
                percent=job.progress_percent,
                stage=job.status,
                message="Job accepted",
                updated_at=job.created_at,
            ),
            created_at=job.created_at,
        )

    async def _append_event(
        self,
        session: AsyncSession,
        job: ExtractionJob,
        event_type: str,
        payload: dict[str, object],
        correlation_id: uuid.UUID,
    ) -> ProgressEvent:
        previous = await session.scalar(
            select(func.max(ProgressEvent.sequence_no)).where(ProgressEvent.job_id == job.id)
        )
        event = ProgressEvent(
            job_id=job.id,
            sequence_no=(previous or 0) + 1,
            event_type=event_type,
            payload=payload,
            correlation_id=correlation_id,
        )
        session.add(event)
        # A browser operation can emit several lifecycle facts in a single transaction.
        # Flush each insert so the next MAX(sequence_no) query sees the durable pending row.
        await session.flush()
        return event

    async def transition(
        self,
        session: AsyncSession,
        *,
        job_id: uuid.UUID,
        expected_state: JobStatus,
        target_state: JobStatus,
        reason: str,
        operation_key: str,
        correlation_id: uuid.UUID,
    ) -> ExtractionJob:
        assert_transition(expected_state, target_state)
        job = await session.scalar(select(ExtractionJob).where(ExtractionJob.id == job_id).with_for_update())
        if job is None or job.status != expected_state.value:
            raise InvalidTransition("The operation has a stale or illegal job state.")
        if job.status in {
            state.value for state in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)
        }:
            raise InvalidTransition("Terminal jobs cannot be mutated.")
        now = utcnow()
        job.status = target_state.value
        job.status_version += 1
        job.updated_at = now
        if target_state == JobStatus.PLANNING and job.started_at is None:
            job.started_at = now
        if target_state in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
            job.completed_at = now
            if target_state == JobStatus.CANCELLED:
                job.progress_percent = min(job.progress_percent, 99)
        event_type = EVENT_FOR_TRANSITION.get(
            (expected_state, target_state),
            "job_failed"
            if target_state == JobStatus.FAILED
            else "job_completed"
            if target_state == JobStatus.COMPLETED
            else "state_transitioned",
        )
        await self._append_event(
            session,
            job,
            event_type,
            {
                "from": expected_state.value,
                "stage": target_state.value,
                "percent": job.progress_percent,
                "message": reason,
                "operation_key": operation_key,
            },
            correlation_id,
        )
        return job

    async def claim_planning(
        self, session: AsyncSession, command: dict[str, object], *, worker_id: str, lease_seconds: int
    ) -> PlanningOperation | None:
        job_id = uuid.UUID(str(command["job_id"]))
        correlation_id = uuid.UUID(str(command["correlation_id"]))
        operation_key = str(command["operation_key"])
        job = await session.scalar(select(ExtractionJob).where(ExtractionJob.id == job_id).with_for_update())
        if job is None or job.status in {
            JobStatus.BROWSER_INITIALIZING.value,
            JobStatus.CANCELLED.value,
            JobStatus.FAILED.value,
        }:
            return None
        if job.status not in {JobStatus.QUEUED.value, JobStatus.PLANNING.value}:
            raise InvalidTransition("Planning command cannot claim the current job state.")
        if job.cancel_requested_at:
            if job.status == JobStatus.QUEUED.value:
                await self.transition(
                    session,
                    job_id=job_id,
                    expected_state=JobStatus.QUEUED,
                    target_state=JobStatus.CANCELLED,
                    reason="Cancellation acknowledged before planning.",
                    operation_key=operation_key,
                    correlation_id=correlation_id,
                )
            else:
                await self.transition(
                    session,
                    job_id=job_id,
                    expected_state=JobStatus.PLANNING,
                    target_state=JobStatus.CANCELLED,
                    reason="Cancellation acknowledged before planning completion.",
                    operation_key=operation_key,
                    correlation_id=correlation_id,
                )
            return None
        if (
            job.status == JobStatus.PLANNING.value
            and job.lease_expires_at
            and job.lease_expires_at > utcnow()
        ):
            return None
        if job.status == JobStatus.QUEUED.value:
            job.progress_percent = max(job.progress_percent, 10)
            await self.transition(
                session,
                job_id=job_id,
                expected_state=JobStatus.QUEUED,
                target_state=JobStatus.PLANNING,
                reason="Validated plan generation started.",
                operation_key=operation_key,
                correlation_id=correlation_id,
            )
        job.lease_owner = worker_id
        job.lease_expires_at = utcnow() + timedelta(seconds=lease_seconds)
        job.last_error_code = None
        job.last_error_message = None
        job.retryable = False
        source = await session.get(Source, job.source_id)
        if source is None:
            raise InvalidTransition("Planning work is missing its source metadata.")
        return PlanningOperation(
            job_id=job.id,
            project_id=job.project_id,
            correlation_id=correlation_id,
            operation_key=operation_key,
            source_url=source.canonical_url,
            task=job.task_description,
            requested_fields=list(job.requested_fields),
            options=dict(job.options),
            output_formats=list(job.output_formats),
        )

    async def complete_planning(
        self,
        session: AsyncSession,
        command: dict[str, object],
        plan: CanonicalPlan,
        *,
        provider_name: str,
        model_name: str,
    ) -> bool:
        """Persist a canonical plan and hand off exactly once to the existing browser boundary."""
        job_id = uuid.UUID(str(command["job_id"]))
        correlation_id = uuid.UUID(str(command["correlation_id"]))
        operation_key = str(command["operation_key"])
        job = await session.scalar(select(ExtractionJob).where(ExtractionJob.id == job_id).with_for_update())
        if job is None or job.status in {JobStatus.BROWSER_INITIALIZING.value, JobStatus.CANCELLED.value}:
            return False
        if job.status != JobStatus.PLANNING.value:
            raise InvalidTransition("Planning completion cannot update the current job state.")
        if job.cancel_requested_at:
            await self.transition(
                session,
                job_id=job_id,
                expected_state=JobStatus.PLANNING,
                target_state=JobStatus.CANCELLED,
                reason="Cancellation acknowledged before plan persistence.",
                operation_key=operation_key,
                correlation_id=correlation_id,
            )
            return False
        existing = await session.scalar(
            select(ExtractionPlan)
            .where(ExtractionPlan.job_id == job_id, ExtractionPlan.version == plan.plan_version)
            .with_for_update()
        )
        if existing is not None:
            raise InvalidTransition("Planning completion encountered an existing plan version.")
        session.add(
            ExtractionPlan(
                job_id=job_id,
                version=plan.plan_version,
                status="DRAFT",
                plan=plan.model_dump(mode="json"),
                model_name=model_name,
                provider_name=provider_name,
                schema_version=plan.schema_version,
                prompt_version=PROMPT_VERSION,
                plan_hash=plan_hash(plan),
            )
        )
        await session.flush()
        job.progress_percent = max(job.progress_percent, 20)
        await self.transition(
            session,
            job_id=job_id,
            expected_state=JobStatus.PLANNING,
            target_state=JobStatus.BROWSER_INITIALIZING,
            reason="Validated canonical plan stored; browser work remains at the Phase 3 capture boundary.",
            operation_key=operation_key,
            correlation_id=correlation_id,
        )
        browser_key = f"job:{job_id}:browser:1"
        session.add(
            WorkOutbox(
                job_id=job_id,
                project_id=job.project_id,
                command_type="run_browser_capture",
                operation_key=browser_key,
                payload={
                    "job_id": str(job_id),
                    "project_id": str(job.project_id),
                    "correlation_id": str(correlation_id),
                    "operation_key": browser_key,
                    "attempt": 1,
                },
            )
        )
        job.lease_owner = None
        job.lease_expires_at = None
        return True

    async def fail_planning(
        self,
        session: AsyncSession,
        command: dict[str, object],
        error: PlannerError,
        *,
        max_retries: int,
    ) -> int | None:
        """Persist a safe planner failure and return the durable retry attempt, if any."""
        job_id = uuid.UUID(str(command["job_id"]))
        correlation_id = uuid.UUID(str(command["correlation_id"]))
        job = await session.scalar(select(ExtractionJob).where(ExtractionJob.id == job_id).with_for_update())
        if job is None or job.status == JobStatus.CANCELLED.value:
            return None
        if job.status != JobStatus.PLANNING.value:
            return None
        if job.cancel_requested_at:
            await self.transition(
                session,
                job_id=job.id,
                expected_state=JobStatus.PLANNING,
                target_state=JobStatus.CANCELLED,
                reason="Planning operation cancelled safely.",
                operation_key=str(command["operation_key"]),
                correlation_id=correlation_id,
            )
            return None
        job.last_error_code = error.code
        job.last_error_message = error.message
        job.retryable = error.retryable
        job.lease_owner = None
        job.lease_expires_at = None
        if error.retryable:
            job.attempt += 1
            if job.attempt <= max_retries:
                await self._append_event(
                    session,
                    job,
                    "planning_retry_scheduled",
                    {
                        "stage": JobStatus.PLANNING.value,
                        "message": "A transient planner failure will be retried.",
                        "attempt": job.attempt,
                    },
                    correlation_id,
                )
                return job.attempt
        await self.transition(
            session,
            job_id=job.id,
            expected_state=JobStatus.PLANNING,
            target_state=JobStatus.FAILED,
            reason=error.message,
            operation_key=str(command["operation_key"]),
            correlation_id=correlation_id,
        )
        return None

    async def prepare_browser_capture(
        self, session: AsyncSession, command: dict[str, object], *, worker_id: str
    ) -> BrowserOperationRequest | None:
        job_id = uuid.UUID(str(command["job_id"]))
        job = await session.scalar(select(ExtractionJob).where(ExtractionJob.id == job_id).with_for_update())
        if job is None or job.status in {JobStatus.CANCELLED.value, JobStatus.FAILED.value}:
            return None
        if job.status != JobStatus.BROWSER_INITIALIZING.value:
            raise InvalidTransition("Browser work cannot claim the current job state.")
        correlation_id = uuid.UUID(str(command["correlation_id"]))
        if job.cancel_requested_at:
            await self.transition(
                session,
                job_id=job_id,
                expected_state=JobStatus.BROWSER_INITIALIZING,
                target_state=JobStatus.CANCELLED,
                reason="Cancellation acknowledged before browser launch.",
                operation_key=str(command["operation_key"]),
                correlation_id=correlation_id,
            )
            return None
        source = await session.get(Source, job.source_id)
        if source is None:
            raise InvalidTransition("Browser work is missing its source metadata.")
        job.lease_owner = worker_id
        job.lease_expires_at = utcnow() + timedelta(seconds=120)
        await self._append_event(
            session,
            job,
            "browser_initializing",
            {"stage": JobStatus.BROWSER_INITIALIZING.value, "message": "Browser capture started."},
            correlation_id,
        )
        return BrowserOperationRequest(
            job_id=str(job.id),
            project_id=str(job.project_id),
            correlation_id=str(correlation_id),
            operation_key=str(command["operation_key"]),
            url=source.canonical_url,
            allowed_domain=source.domain,
            capture_screenshot=True,
        )

    async def claim_discovery(
        self, session: AsyncSession, command: dict[str, object], *, worker_id: str, lease_seconds: int
    ) -> DiscoveryOperation | None:
        """Claim one durable inventory page. Discovery owns URL inventory, never record creation."""
        job_id = uuid.UUID(str(command["job_id"]))
        correlation_id = uuid.UUID(str(command["correlation_id"]))
        job = await session.scalar(select(ExtractionJob).where(ExtractionJob.id == job_id).with_for_update())
        if job is None or job.status in {JobStatus.CANCELLED.value, JobStatus.FAILED.value}:
            return None
        if job.status != JobStatus.DISCOVERING.value:
            raise InvalidTransition("Discovery command cannot claim the current job state.")
        if job.cancel_requested_at:
            await self.transition(
                session,
                job_id=job.id,
                expected_state=JobStatus.DISCOVERING,
                target_state=JobStatus.CANCELLED,
                reason="Cancellation acknowledged before discovery.",
                operation_key=str(command["operation_key"]),
                correlation_id=correlation_id,
            )
            return None
        requested_page_id = command.get("page_id")
        query = select(Page).where(Page.job_id == job.id, Page.status == InventoryStatus.DISCOVERED.value)
        if requested_page_id:
            query = query.where(Page.id == uuid.UUID(str(requested_page_id)))
        page = await session.scalar(
            query.order_by(Page.depth, Page.discovered_at, Page.id).with_for_update(skip_locked=True)
        )
        if page is None:
            return None
        plan_row = await session.scalar(
            select(ExtractionPlan)
            .where(ExtractionPlan.job_id == job.id)
            .order_by(ExtractionPlan.version.desc())
            .limit(1)
        )
        source = await session.get(Source, job.source_id)
        if plan_row is None or source is None:
            raise InvalidTransition("Discovery work is missing a validated plan or source metadata.")
        plan = CanonicalPlan.model_validate(plan_row.plan)
        page.status = InventoryStatus.QUEUED.value
        job.lease_owner = worker_id
        job.lease_expires_at = utcnow() + timedelta(seconds=lease_seconds)
        await self._append_event(
            session,
            job,
            "page_queued",
            {"stage": JobStatus.DISCOVERING.value, "page_id": str(page.id), "depth": page.depth},
            correlation_id,
        )
        return DiscoveryOperation(
            job_id=job.id,
            project_id=job.project_id,
            correlation_id=correlation_id,
            operation_key=str(command["operation_key"]),
            page_id=page.id,
            page_url=page.canonical_url,
            page_canonical_url=page.canonical_url,
            page_depth=page.depth,
            page_method=page.discovered_via,
            source_domain=source.domain,
            plan=plan,
        )

    async def complete_discovery_page(
        self,
        session: AsyncSession,
        command: dict[str, object],
        operation: DiscoveryOperation,
        result: BrowserOperationResult,
        *,
        discovery: DiscoveryService,
    ) -> None:
        job = await session.scalar(
            select(ExtractionJob).where(ExtractionJob.id == operation.job_id).with_for_update()
        )
        if job is None or job.status in {JobStatus.CANCELLED.value, JobStatus.FAILED.value}:
            return
        if job.status != JobStatus.DISCOVERING.value:
            raise InvalidTransition("Discovery completion cannot update the current job state.")
        if job.cancel_requested_at:
            await self.transition(
                session,
                job_id=job.id,
                expected_state=JobStatus.DISCOVERING,
                target_state=JobStatus.CANCELLED,
                reason="Cancellation acknowledged after discovery navigation.",
                operation_key=operation.operation_key,
                correlation_id=operation.correlation_id,
            )
            return
        page = await session.scalar(select(Page).where(Page.id == operation.page_id).with_for_update())
        if page is None:
            raise InvalidTransition("Discovery completion is missing its inventory page.")
        page.status = InventoryStatus.VISITED.value
        page.final_url = result.navigation.final_url
        page.http_status = result.navigation.status
        page.content_type = result.navigation.content_type
        page.title = result.navigation.title
        page.navigation_time_ms = result.navigation.navigation_time_ms
        page.redirect_count = result.navigation.redirect_count
        page.visited_at = utcnow()
        page.discovery_metadata = {"signal_count": len(result.navigation_signals)}
        job.pages_processed += 1
        await self._append_event(
            session,
            job,
            "page_visited",
            {"stage": JobStatus.DISCOVERING.value, "page_id": str(page.id), "depth": page.depth},
            operation.correlation_id,
        )
        seen = set((await session.scalars(select(Page.canonical_url).where(Page.job_id == job.id))).all())
        signals = tuple(
            NavigationSignal(signal.href, signal.text, signal.rel, signal.aria_label)
            for signal in result.navigation_signals
        )
        decision = discovery.from_signals(
            plan=operation.plan,
            parent_url=result.navigation.final_url,
            parent_canonical_url=page.canonical_url,
            parent_depth=page.depth,
            signals=signals,
            seen_urls=seen,
        )
        if page.discovered_via == DiscoveryMethod.SITEMAP.value and result.document_text:
            sitemap = discovery.sitemap_candidates(
                plan=operation.plan,
                sitemap_text=result.document_text,
                parent_canonical_url=page.canonical_url,
                parent_depth=page.depth,
                seen_urls=seen,
            )
            decision = type(decision)(
                candidates=decision.candidates + sitemap.candidates,
                rejected=decision.rejected + sitemap.rejected,
                duplicate_count=decision.duplicate_count + sitemap.duplicate_count,
            )
        await self._persist_discovery_candidates(
            session, job, operation, page, decision.candidates, False, discovery
        )
        await self._persist_discovery_candidates(
            session, job, operation, page, decision.rejected, True, discovery
        )
        if decision.duplicate_count:
            await self._append_event(
                session,
                job,
                "page_duplicate",
                {"stage": JobStatus.DISCOVERING.value, "count": decision.duplicate_count},
                operation.correlation_id,
            )
        if self._should_enqueue_sitemap(discovery, operation, page, seen):
            sitemap_url = discovery.default_sitemap_url(operation.plan.source.url)
            if sitemap_url:
                candidate = DiscoveryCandidate(
                    url=sitemap_url,
                    canonical_url=sitemap_url,
                    discovered_via=DiscoveryMethod.SITEMAP,
                    depth=1,
                    parent_canonical_url=page.canonical_url,
                    policy_decision="ALLOWED",
                    relevance_reason="configured sitemap probe",
                )
                await self._persist_discovery_candidates(
                    session, job, operation, page, (candidate,), False, discovery
                )
        job.lease_owner = None
        job.lease_expires_at = None
        next_page = await session.scalar(
            select(Page)
            .where(Page.job_id == job.id, Page.status == InventoryStatus.DISCOVERED.value)
            .order_by(Page.depth, Page.discovered_at, Page.id)
            .limit(1)
        )
        if next_page is None:
            job.progress_percent = max(job.progress_percent, 40)
            await self._append_event(
                session,
                job,
                "discovery_completed",
                {"stage": JobStatus.DISCOVERING.value, "pages_discovered": job.pages_discovered},
                operation.correlation_id,
            )
            await self.transition(
                session,
                job_id=job.id,
                expected_state=JobStatus.DISCOVERING,
                target_state=JobStatus.EXTRACTING,
                reason="Discovery inventory completed; extraction work is ready.",
                operation_key=operation.operation_key,
                correlation_id=operation.correlation_id,
            )
            extraction_key = f"job:{job.id}:extraction:1"
            session.add(
                WorkOutbox(
                    job_id=job.id,
                    project_id=job.project_id,
                    command_type="run_extraction",
                    operation_key=extraction_key,
                    payload={
                        "job_id": str(job.id),
                        "project_id": str(job.project_id),
                        "correlation_id": str(operation.correlation_id),
                        "operation_key": extraction_key,
                        "attempt": 1,
                    },
                )
            )
            return
        self._queue_discovery_page(session, job, next_page, operation.correlation_id)

    async def _persist_discovery_candidates(
        self,
        session: AsyncSession,
        job: ExtractionJob,
        operation: DiscoveryOperation,
        parent: Page,
        candidates: tuple[DiscoveryCandidate, ...],
        rejected: bool,
        discovery: DiscoveryService,
    ) -> None:
        accepted = await session.scalar(
            select(func.count())
            .select_from(Page)
            .where(
                Page.job_id == job.id,
                Page.status.not_in([InventoryStatus.REJECTED.value, InventoryStatus.DUPLICATE.value]),
            )
        )
        accepted_count = int(accepted or 0)
        for candidate in candidates:
            existing = await session.scalar(
                select(Page).where(Page.job_id == job.id, Page.canonical_url == candidate.canonical_url)
            )
            if existing:
                await self._append_event(
                    session,
                    job,
                    "page_duplicate",
                    {"stage": JobStatus.DISCOVERING.value, "url": candidate.canonical_url},
                    operation.correlation_id,
                )
                continue
            status = InventoryStatus.REJECTED.value if rejected else InventoryStatus.DISCOVERED.value
            if not rejected and accepted_count >= min(
                discovery.settings.discovery_max_pages, operation.plan.limits.max_pages
            ):
                status = InventoryStatus.SKIPPED.value
            candidate_page = Page(
                job_id=job.id,
                url=candidate.url,
                canonical_url=candidate.canonical_url,
                status=status,
                discovered_at=utcnow(),
                discovered_via=candidate.discovered_via.value,
                depth=candidate.depth,
                parent_page_id=parent.id,
                deduplication_key=hashlib.sha256(candidate.canonical_url.encode()).hexdigest(),
                policy_decision=candidate.policy_decision,
                relevance_score=candidate.relevance_score,
                relevance_reason=candidate.relevance_reason,
            )
            session.add(candidate_page)
            if status == InventoryStatus.DISCOVERED.value:
                accepted_count += 1
                job.pages_discovered += 1
                await self._append_event(
                    session,
                    job,
                    "pagination_detected"
                    if candidate.discovered_via == DiscoveryMethod.PAGINATION
                    else "page_discovered",
                    {
                        "stage": JobStatus.DISCOVERING.value,
                        "url": candidate.canonical_url,
                        "depth": candidate.depth,
                        "method": candidate.discovered_via.value,
                    },
                    operation.correlation_id,
                )
            elif status == InventoryStatus.REJECTED.value:
                await self._append_event(
                    session,
                    job,
                    "page_rejected",
                    {
                        "stage": JobStatus.DISCOVERING.value,
                        "url": candidate.canonical_url,
                        "reason": candidate.policy_decision,
                    },
                    operation.correlation_id,
                )
            else:
                await self._append_event(
                    session,
                    job,
                    "page_rejected",
                    {"stage": JobStatus.DISCOVERING.value, "reason": "DISCOVERY_LIMIT_REACHED"},
                    operation.correlation_id,
                )

    @staticmethod
    def _should_enqueue_sitemap(
        discovery: DiscoveryService, operation: DiscoveryOperation, page: Page, seen: set[str]
    ) -> bool:
        sitemap_url = discovery.default_sitemap_url(operation.plan.source.url)
        return bool(
            discovery.settings.discovery_enable_sitemaps
            and page.depth == 0
            and sitemap_url
            and sitemap_url not in seen
        )

    @staticmethod
    def _queue_discovery_page(
        session: AsyncSession, job: ExtractionJob, page: Page, correlation_id: uuid.UUID
    ) -> None:
        key = f"job:{job.id}:discovery:page:{page.id}:1"
        session.add(
            WorkOutbox(
                job_id=job.id,
                project_id=job.project_id,
                command_type="run_discovery",
                operation_key=key,
                payload={
                    "job_id": str(job.id),
                    "project_id": str(job.project_id),
                    "correlation_id": str(correlation_id),
                    "operation_key": key,
                    "page_id": str(page.id),
                    "attempt": 1,
                },
            )
        )

    async def fail_discovery(
        self, session: AsyncSession, command: dict[str, object], error: DiscoveryError, *, max_attempts: int
    ) -> int | None:
        """Persist a stable discovery failure; retries retain the inventory entry and never create a record."""
        job_id = uuid.UUID(str(command["job_id"]))
        correlation_id = uuid.UUID(str(command["correlation_id"]))
        job = await session.scalar(select(ExtractionJob).where(ExtractionJob.id == job_id).with_for_update())
        if job is None or job.status in {JobStatus.CANCELLED.value, JobStatus.FAILED.value}:
            return None
        if job.status != JobStatus.DISCOVERING.value:
            return None
        page_id = command.get("page_id")
        page = (
            await session.scalar(select(Page).where(Page.id == uuid.UUID(str(page_id))).with_for_update())
            if page_id
            else None
        )
        if job.cancel_requested_at:
            if page is not None:
                page.status = InventoryStatus.SKIPPED.value
            await self.transition(
                session,
                job_id=job.id,
                expected_state=JobStatus.DISCOVERING,
                target_state=JobStatus.CANCELLED,
                reason="Discovery operation cancelled safely.",
                operation_key=str(command["operation_key"]),
                correlation_id=correlation_id,
            )
            return None
        if page is not None:
            page.status = InventoryStatus.FAILED.value
        job.last_error_code = error.code
        job.last_error_message = error.message
        job.retryable = error.retryable
        job.lease_owner = None
        job.lease_expires_at = None
        if error.retryable:
            job.attempt += 1
            if job.attempt <= max_attempts:
                if page is not None:
                    page.status = InventoryStatus.DISCOVERED.value
                await self._append_event(
                    session,
                    job,
                    "discovery_retry_scheduled",
                    {"stage": JobStatus.DISCOVERING.value, "attempt": job.attempt, "page_id": str(page_id)},
                    correlation_id,
                )
                return job.attempt
        await self._append_event(
            session,
            job,
            "discovery_failed",
            {"stage": JobStatus.DISCOVERING.value, "code": error.code, "page_id": str(page_id)},
            correlation_id,
        )
        await self.transition(
            session,
            job_id=job.id,
            expected_state=JobStatus.DISCOVERING,
            target_state=JobStatus.FAILED,
            reason=error.message,
            operation_key=str(command["operation_key"]),
            correlation_id=correlation_id,
        )
        return None

    async def claim_extraction(
        self, session: AsyncSession, command: dict[str, object], *, worker_id: str, lease_seconds: int
    ) -> ExtractionOperation | None:
        """Claim exactly one visited Phase 5 inventory page; never creates or discovers URLs."""
        job_id = uuid.UUID(str(command["job_id"]))
        correlation_id = uuid.UUID(str(command["correlation_id"]))
        job = await session.scalar(select(ExtractionJob).where(ExtractionJob.id == job_id).with_for_update())
        if job is None or job.status in {JobStatus.CANCELLED.value, JobStatus.FAILED.value}:
            return None
        if job.status != JobStatus.EXTRACTING.value:
            raise InvalidTransition("Extraction command cannot claim the current job state.")
        if job.cancel_requested_at:
            await self.transition(
                session,
                job_id=job.id,
                expected_state=JobStatus.EXTRACTING,
                target_state=JobStatus.CANCELLED,
                reason="Cancellation acknowledged before extraction.",
                operation_key=str(command["operation_key"]),
                correlation_id=correlation_id,
            )
            return None
        requested_page_id = command.get("page_id")
        query = select(Page).where(
            Page.job_id == job.id,
            Page.status == InventoryStatus.VISITED.value,
            (Page.extraction_status.is_(None)) | (Page.extraction_status == "PENDING"),
        )
        if requested_page_id:
            query = query.where(Page.id == uuid.UUID(str(requested_page_id)))
        page = await session.scalar(
            query.order_by(Page.depth, Page.visited_at, Page.id).with_for_update(skip_locked=True)
        )
        if page is None:
            return None
        plan_row = await session.scalar(
            select(ExtractionPlan)
            .where(ExtractionPlan.job_id == job.id)
            .order_by(ExtractionPlan.version.desc())
            .limit(1)
        )
        source = await session.get(Source, job.source_id)
        if plan_row is None or source is None:
            raise InvalidTransition("Extraction work is missing a canonical plan or source metadata.")
        page.extraction_status = "EXTRACTING"
        page.extraction_started_at = utcnow()
        job.lease_owner = worker_id
        job.lease_expires_at = utcnow() + timedelta(seconds=lease_seconds)
        await self._append_event(
            session,
            job,
            "page_extraction_started",
            {"stage": JobStatus.EXTRACTING.value, "page_id": str(page.id)},
            correlation_id,
        )
        return ExtractionOperation(
            job_id=job.id,
            project_id=job.project_id,
            correlation_id=correlation_id,
            operation_key=str(command["operation_key"]),
            page_id=page.id,
            page_url=page.canonical_url,
            source_domain=source.domain,
            plan=CanonicalPlan.model_validate(plan_row.plan),
        )

    async def complete_extraction_page(
        self,
        session: AsyncSession,
        command: dict[str, object],
        operation: ExtractionOperation,
        result: ExtractionResult,
        *,
        server_max_records: int = 10_000,
    ) -> None:
        job = await session.scalar(
            select(ExtractionJob).where(ExtractionJob.id == operation.job_id).with_for_update()
        )
        if job is None or job.status in {JobStatus.CANCELLED.value, JobStatus.FAILED.value}:
            return
        if job.status != JobStatus.EXTRACTING.value:
            raise InvalidTransition("Extraction completion cannot update the current job state.")
        if job.cancel_requested_at:
            await self.transition(
                session,
                job_id=job.id,
                expected_state=JobStatus.EXTRACTING,
                target_state=JobStatus.CANCELLED,
                reason="Cancellation acknowledged before record persistence.",
                operation_key=operation.operation_key,
                correlation_id=operation.correlation_id,
            )
            return
        page = await session.scalar(select(Page).where(Page.id == operation.page_id).with_for_update())
        if page is None:
            raise InvalidTransition("Extraction completion is missing its inventory page.")
        allowed = min(operation.plan.limits.max_records, server_max_records)
        existing_count = (
            await session.scalar(select(func.count()).select_from(Record).where(Record.job_id == job.id)) or 0
        )
        created = 0
        for extracted in result.records[: max(0, allowed - int(existing_count))]:
            payload = {
                "schema_version": "records.v1",
                "record_id": extracted.identity,
                "plan_version": operation.plan.plan_version,
                "fields": {
                    name: {
                        "raw": field.raw_value,
                        "value": field.value,
                        "type": field.field_type,
                        "strategy": field.strategy,
                        "confidence": field.confidence,
                        "missing": field.missing,
                        "evidence": (
                            {
                                "source_text": field.evidence.source_text,
                                "location": field.evidence.location,
                                "attribute": field.evidence.attribute,
                                "structured_path": field.evidence.structured_path,
                            }
                            if field.evidence
                            else None
                        ),
                    }
                    for name, field in extracted.fields.items()
                },
                "provenance": extracted.provenance,
            }
            record = Record(
                job_id=job.id,
                page_id=page.id,
                payload=payload,
                content_hash=hashlib.sha256(
                    json.dumps(payload, sort_keys=True, default=str).encode()
                ).hexdigest(),
                confidence=extracted.confidence,
                record_identity=extracted.identity,
                plan_version=operation.plan.plan_version,
                strategy=extracted.strategy,
                provenance=extracted.provenance,
                extraction_metadata={"document_truncated": result.document_truncated},
            )
            try:
                async with session.begin_nested():
                    session.add(record)
                    await session.flush()
                created += 1
            except IntegrityError:
                await self._append_event(
                    session,
                    job,
                    "record_duplicate",
                    {"stage": JobStatus.EXTRACTING.value, "page_id": str(page.id)},
                    operation.correlation_id,
                )
        page.extraction_status = "EXTRACTED" if created else "PARTIAL"
        page.extraction_completed_at = utcnow()
        page.extraction_metadata = {
            "records_created": created,
            "warnings": list(result.warnings),
            "truncated": result.document_truncated,
        }
        job.records_found += created
        job.pages_processed += 1
        for warning in result.warnings[:10]:
            await self._append_event(
                session,
                job,
                "field_extraction_warning",
                {"stage": JobStatus.EXTRACTING.value, "page_id": str(page.id), "warning": warning},
                operation.correlation_id,
            )
        await self._append_event(
            session,
            job,
            "page_extraction_completed",
            {"stage": JobStatus.EXTRACTING.value, "page_id": str(page.id), "records_created": created},
            operation.correlation_id,
        )
        job.lease_owner = None
        job.lease_expires_at = None
        next_page = await session.scalar(
            select(Page)
            .where(
                Page.job_id == job.id,
                Page.status == InventoryStatus.VISITED.value,
                Page.extraction_status.is_(None),
            )
            .order_by(Page.depth, Page.visited_at, Page.id)
            .limit(1)
        )
        if next_page is None:
            job.progress_percent = max(job.progress_percent, 60)
            await self._append_event(
                session,
                job,
                "extraction_completed",
                {"stage": JobStatus.EXTRACTING.value, "records_found": job.records_found},
                operation.correlation_id,
            )
            await self.transition(
                session,
                job_id=job.id,
                expected_state=JobStatus.EXTRACTING,
                target_state=JobStatus.VALIDATING,
                reason="Extraction records persisted; validation remains a Phase 7 boundary.",
                operation_key=operation.operation_key,
                correlation_id=operation.correlation_id,
            )
            return
        self._queue_extraction_page(
            session, job, next_page, operation.correlation_id, operation.plan.plan_version
        )

    @staticmethod
    def _queue_extraction_page(
        session: AsyncSession, job: ExtractionJob, page: Page, correlation_id: uuid.UUID, plan_version: int
    ) -> None:
        key = f"job:{job.id}:extraction:page:{page.id}:{plan_version}"
        session.add(
            WorkOutbox(
                job_id=job.id,
                project_id=job.project_id,
                command_type="run_extraction",
                operation_key=key,
                payload={
                    "job_id": str(job.id),
                    "project_id": str(job.project_id),
                    "correlation_id": str(correlation_id),
                    "operation_key": key,
                    "page_id": str(page.id),
                    "plan_version": plan_version,
                    "attempt": 1,
                },
            )
        )

    async def fail_extraction(
        self, session: AsyncSession, command: dict[str, object], error: ExtractionError, *, max_attempts: int
    ) -> int | None:
        job_id = uuid.UUID(str(command["job_id"]))
        correlation_id = uuid.UUID(str(command["correlation_id"]))
        job = await session.scalar(select(ExtractionJob).where(ExtractionJob.id == job_id).with_for_update())
        if job is None or job.status in {JobStatus.CANCELLED.value, JobStatus.FAILED.value}:
            return None
        if job.status != JobStatus.EXTRACTING.value:
            return None
        page_id = command.get("page_id")
        page = await session.get(Page, uuid.UUID(str(page_id))) if page_id else None
        if job.cancel_requested_at:
            if page:
                page.extraction_status = "SKIPPED"
            await self.transition(
                session,
                job_id=job.id,
                expected_state=JobStatus.EXTRACTING,
                target_state=JobStatus.CANCELLED,
                reason="Extraction cancelled safely.",
                operation_key=str(command["operation_key"]),
                correlation_id=correlation_id,
            )
            return None
        if page:
            page.extraction_status = "FAILED"
        job.last_error_code, job.last_error_message, job.retryable = (
            error.code,
            error.message,
            error.retryable,
        )
        job.lease_owner = job.lease_expires_at = None
        if error.retryable:
            job.attempt += 1
            if job.attempt <= max_attempts:
                if page:
                    page.extraction_status = "PENDING"
                await self._append_event(
                    session,
                    job,
                    "extraction_retry_scheduled",
                    {"stage": JobStatus.EXTRACTING.value, "attempt": job.attempt},
                    correlation_id,
                )
                return job.attempt
        await self._append_event(
            session,
            job,
            "page_extraction_failed",
            {"stage": JobStatus.EXTRACTING.value, "code": error.code},
            correlation_id,
        )
        await self.transition(
            session,
            job_id=job.id,
            expected_state=JobStatus.EXTRACTING,
            target_state=JobStatus.FAILED,
            reason=error.message,
            operation_key=str(command["operation_key"]),
            correlation_id=correlation_id,
        )
        return None

    async def complete_browser_capture(
        self, session: AsyncSession, command: dict[str, object], result: BrowserOperationResult
    ) -> None:
        job_id = uuid.UUID(str(command["job_id"]))
        correlation_id = uuid.UUID(str(command["correlation_id"]))
        job = await session.scalar(select(ExtractionJob).where(ExtractionJob.id == job_id).with_for_update())
        if job is None or job.status in {JobStatus.CANCELLED.value, JobStatus.FAILED.value}:
            return
        if job.status != JobStatus.BROWSER_INITIALIZING.value:
            raise InvalidTransition("Browser completion cannot update the current job state.")
        if job.cancel_requested_at:
            await self.transition(
                session,
                job_id=job_id,
                expected_state=JobStatus.BROWSER_INITIALIZING,
                target_state=JobStatus.CANCELLED,
                reason="Cancellation acknowledged after browser cleanup.",
                operation_key=str(command["operation_key"]),
                correlation_id=correlation_id,
            )
            return
        navigation = result.navigation
        page = await session.scalar(
            select(Page)
            .where(Page.job_id == job.id, Page.canonical_url == navigation.final_url)
            .with_for_update()
        )
        if page is None:
            page = Page(
                job_id=job.id,
                url=navigation.requested_url,
                canonical_url=navigation.final_url,
                status="CAPTURED",
            )
            session.add(page)
            await session.flush()
        page.status = InventoryStatus.DISCOVERED.value
        page.final_url = navigation.final_url
        page.http_status = navigation.status
        page.content_type = navigation.content_type
        page.title = navigation.title
        page.viewport = navigation.viewport
        page.navigation_time_ms = navigation.navigation_time_ms
        page.redirect_count = navigation.redirect_count
        page.browser_metadata = {"phase": 3, "event_count": len(result.events)}
        page.captured_at = utcnow()
        page.discovered_at = page.discovered_at or utcnow()
        page.discovered_via = DiscoveryMethod.SOURCE.value
        page.depth = 0
        page.policy_decision = "ALLOWED"
        page.deduplication_key = hashlib.sha256(page.canonical_url.encode()).hexdigest()
        job.pages_discovered = max(job.pages_discovered, 1)
        job.pages_processed = max(job.pages_processed, 1)
        for browser_artifact in result.artifacts:
            ref = browser_artifact.artifact
            session.add(
                BrowserArtifact(
                    job_id=job.id,
                    page_id=page.id,
                    artifact_type=browser_artifact.kind,
                    storage_key=ref.key,
                    media_type=ref.media_type,
                    byte_size=ref.byte_size,
                    checksum=ref.checksum,
                    expires_at=ref.expires_at,
                )
            )
        for event in result.events:
            await self._append_event(
                session,
                job,
                str(event.get("type", "browser_event")),
                {"stage": JobStatus.BROWSER_INITIALIZING.value, "message": "Browser lifecycle checkpoint."},
                correlation_id,
            )
        await self._append_event(
            session,
            job,
            "browser_completed",
            {
                "stage": JobStatus.BROWSER_INITIALIZING.value,
                "message": "Browser navigation completed at the Phase 3 boundary.",
                "page_id": str(page.id),
            },
            correlation_id,
        )
        job.progress_percent = max(job.progress_percent, 30)
        await self.transition(
            session,
            job_id=job.id,
            expected_state=JobStatus.BROWSER_INITIALIZING,
            target_state=JobStatus.DISCOVERING,
            reason="Browser capture completed; discovery inventory is ready to begin.",
            operation_key=str(command["operation_key"]),
            correlation_id=correlation_id,
        )
        discovery_key = f"job:{job.id}:discovery:source:1"
        session.add(
            WorkOutbox(
                job_id=job.id,
                project_id=job.project_id,
                command_type="run_discovery",
                operation_key=discovery_key,
                payload={
                    "job_id": str(job.id),
                    "project_id": str(job.project_id),
                    "correlation_id": str(correlation_id),
                    "operation_key": discovery_key,
                    "page_id": str(page.id),
                    "attempt": 1,
                },
            )
        )
        job.lease_owner = None
        job.lease_expires_at = None

    async def fail_browser_capture(
        self, session: AsyncSession, command: dict[str, object], error: BrowserEngineError
    ) -> bool:
        """Persist a browser failure and report whether the worker may retry it."""
        job_id = uuid.UUID(str(command["job_id"]))
        correlation_id = uuid.UUID(str(command["correlation_id"]))
        job = await session.scalar(select(ExtractionJob).where(ExtractionJob.id == job_id).with_for_update())
        if job is None or job.status == JobStatus.CANCELLED.value:
            return False
        if isinstance(error, BrowserCancelled) or job.cancel_requested_at:
            if job.status == JobStatus.BROWSER_INITIALIZING.value:
                await self.transition(
                    session,
                    job_id=job.id,
                    expected_state=JobStatus.BROWSER_INITIALIZING,
                    target_state=JobStatus.CANCELLED,
                    reason="Browser operation cancelled safely.",
                    operation_key=str(command["operation_key"]),
                    correlation_id=correlation_id,
                )
            return False
        job.last_error_code = error.code
        job.last_error_message = error.message
        job.retryable = error.retryable
        job.lease_owner = None
        job.lease_expires_at = None
        if error.retryable and int(command.get("attempt", 1)) < job.max_attempts:
            await self._append_event(
                session,
                job,
                "browser_retry_scheduled",
                {
                    "stage": JobStatus.BROWSER_INITIALIZING.value,
                    "message": "A transient browser failure will be retried.",
                },
                correlation_id,
            )
            return True
        await self.transition(
            session,
            job_id=job.id,
            expected_state=JobStatus.BROWSER_INITIALIZING,
            target_state=JobStatus.FAILED,
            reason=error.message,
            operation_key=str(command["operation_key"]),
            correlation_id=correlation_id,
        )
        return False

    async def cancel(
        self, session: AsyncSession, *, job_id: uuid.UUID, principal_id: uuid.UUID, correlation_id: uuid.UUID
    ) -> CancelResponse:
        job = await self.get_job(session, job_id, principal_id)
        if job.status == JobStatus.COMPLETED.value:
            raise InvalidTransition("Completed jobs cannot be cancelled.")
        if job.status == JobStatus.CANCELLED.value:
            return CancelResponse(job_id=job.id, status=job.status, cancelled_at=job.completed_at)
        if job.status == JobStatus.FAILED.value:
            raise InvalidTransition("Failed jobs cannot be cancelled.")
        job.cancel_requested_at, job.cancelled_by = utcnow(), principal_id
        await self.transition(
            session,
            job_id=job.id,
            expected_state=JobStatus(job.status),
            target_state=JobStatus.CANCELLED,
            reason="Cancellation requested by project principal.",
            operation_key=f"job:{job.id}:cancel",
            correlation_id=correlation_id,
        )
        return CancelResponse(job_id=job.id, status=JobStatus.CANCELLED.value, cancelled_at=job.completed_at)

    async def status(
        self, session: AsyncSession, *, job_id: uuid.UUID, principal_id: uuid.UUID
    ) -> JobStatusResponse:
        job = await self.get_job(session, job_id, principal_id)
        plan = await session.scalar(
            select(ExtractionPlan)
            .where(ExtractionPlan.job_id == job.id)
            .order_by(ExtractionPlan.version.desc())
            .limit(1)
        )
        error = None
        if job.last_error_code:
            from wde_api.schemas import ErrorProjection

            error = ErrorProjection(
                code=job.last_error_code,
                message=job.last_error_message or "Job failed safely.",
                retryable=job.retryable,
                correlation_id=job.correlation_id,
            )
        return JobStatusResponse(
            job_id=job.id,
            status=job.status,
            progress=ProgressProjection(
                percent=job.progress_percent,
                stage=job.status,
                pages_discovered=job.pages_discovered,
                pages_processed=job.pages_processed,
                records_found=job.records_found,
                records_valid=job.records_valid,
                updated_at=job.updated_at,
            ),
            plan=(
                PlanProjection(
                    version=plan.version,
                    status=plan.status,
                    schema_version=plan.schema_version,
                    model_name=plan.model_name,
                    plan_hash=plan.plan_hash,
                    created_at=plan.created_at,
                )
                if plan
                else None
            ),
            error=error,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )

    async def results(
        self, session: AsyncSession, *, job_id: uuid.UUID, principal_id: uuid.UUID, page: int, page_size: int
    ) -> ResultsResponse:
        job = await self.get_job(session, job_id, principal_id)
        plan = await session.scalar(
            select(ExtractionPlan)
            .where(ExtractionPlan.job_id == job.id)
            .order_by(ExtractionPlan.version.desc())
            .limit(1)
        )
        records = (
            await session.scalars(
                select(Record).where(Record.job_id == job.id).offset((page - 1) * page_size).limit(page_size)
            )
        ).all()
        total = (
            await session.scalar(select(func.count()).select_from(Record).where(Record.job_id == job.id)) or 0
        )
        return ResultsResponse(
            job_id=job.id,
            plan_version=plan.version if plan else None,
            items=[
                {
                    "record_id": item.id,
                    "data": item.payload,
                    "validation": "PENDING",
                    "source_page_id": item.page_id,
                }
                for item in records
            ],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def pages(
        self, session: AsyncSession, *, job_id: uuid.UUID, principal_id: uuid.UUID, page: int, page_size: int
    ):
        """Return safe inventory metadata only; discovery does not expose page body content or worker commands."""
        from wde_api.schemas import PageInventoryItem, PageInventoryResponse

        job = await self.get_job(session, job_id, principal_id)
        items = (
            await session.scalars(
                select(Page)
                .where(Page.job_id == job.id)
                .order_by(Page.depth, Page.discovered_at, Page.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        total = await session.scalar(select(func.count()).select_from(Page).where(Page.job_id == job.id)) or 0
        return PageInventoryResponse(
            job_id=job.id,
            items=[
                PageInventoryItem(
                    page_id=item.id,
                    url=item.url,
                    canonical_url=item.canonical_url,
                    status=item.status,
                    discovered_via=item.discovered_via,
                    depth=item.depth,
                    parent_page_id=item.parent_page_id,
                    discovered_at=item.discovered_at,
                    visited_at=item.visited_at,
                    http_status=item.http_status,
                    content_type=item.content_type,
                    title=item.title,
                    policy_decision=item.policy_decision,
                    relevance_score=item.relevance_score,
                    relevance_reason=item.relevance_reason,
                )
                for item in items
            ],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def files(
        self, session: AsyncSession, *, job_id: uuid.UUID, principal_id: uuid.UUID
    ) -> FilesResponse:
        await self.get_job(session, job_id, principal_id)
        return FilesResponse(job_id=job_id, files=[])

    async def events_after(
        self, session: AsyncSession, *, job_id: uuid.UUID, after_sequence: int
    ) -> list[ProgressEvent]:
        return (
            await session.scalars(
                select(ProgressEvent)
                .where(ProgressEvent.job_id == job_id, ProgressEvent.sequence_no > after_sequence)
                .order_by(ProgressEvent.sequence_no)
            )
        ).all()

    async def recover_expired_leases(self, session: AsyncSession) -> int:
        expired = (
            await session.scalars(
                select(ExtractionJob)
                .where(
                    ExtractionJob.status.in_([state.value for state in ACTIVE_STATES]),
                    ExtractionJob.lease_expires_at < utcnow(),
                )
                .with_for_update(skip_locked=True)
            )
        ).all()
        recovered = 0
        for job in expired:
            if job.cancel_requested_at:
                continue
            job.lease_owner, job.lease_expires_at = None, None
            job.attempt += 1
            if job.attempt > job.max_attempts:
                job.status = JobStatus.FAILED.value
                job.last_error_code, job.last_error_message, job.completed_at = (
                    "INTERNAL_ERROR",
                    "Worker lease expired after the retry budget.",
                    utcnow(),
                )
                await self._append_event(
                    session,
                    job,
                    "job_failed",
                    {"stage": job.status, "message": job.last_error_message},
                    job.correlation_id,
                )
                continue
            phase = (
                "browser"
                if job.status == JobStatus.BROWSER_INITIALIZING.value
                else "discovery"
                if job.status == JobStatus.DISCOVERING.value
                else "planning"
            )
            command_type = (
                "run_browser_capture"
                if phase == "browser"
                else "run_discovery"
                if phase == "discovery"
                else "run_planning"
            )
            key = f"job:{job.id}:{phase}:{job.attempt}"
            page = None
            if phase == "discovery":
                page = await session.scalar(
                    select(Page)
                    .where(
                        Page.job_id == job.id,
                        Page.status.in_([InventoryStatus.QUEUED.value, InventoryStatus.DISCOVERED.value]),
                    )
                    .order_by(Page.depth, Page.discovered_at, Page.id)
                    .with_for_update(skip_locked=True)
                )
                if page is None:
                    continue
                page.status = InventoryStatus.DISCOVERED.value
            session.add(
                WorkOutbox(
                    job_id=job.id,
                    project_id=job.project_id,
                    command_type=command_type,
                    operation_key=key,
                    attempt=job.attempt,
                    available_at=utcnow() + timedelta(seconds=retry_delay_seconds(job.attempt)),
                    payload={
                        "job_id": str(job.id),
                        "project_id": str(job.project_id),
                        "correlation_id": str(job.correlation_id),
                        "operation_key": key,
                        "attempt": job.attempt,
                        **({"page_id": str(page.id)} if page is not None else {}),
                    },
                )
            )
            recovered += 1
        return recovered
