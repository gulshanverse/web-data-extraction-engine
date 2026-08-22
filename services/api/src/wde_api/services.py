"""Application service and orchestrator for durable Phase 2 jobs. Future engines are represented only by a deterministic planning placeholder."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from wde_api.auth import NotAuthorized
from wde_api.browser_errors import BrowserCancelled, BrowserEngineError
from wde_api.browser_types import BrowserOperationRequest, BrowserOperationResult
from wde_api.domain import (
    ACTIVE_STATES,
    EVENT_FOR_TRANSITION,
    InvalidTransition,
    JobStatus,
    assert_transition,
    retry_delay_seconds,
)
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

    async def process_planning_placeholder(
        self, session: AsyncSession, command: dict[str, object], *, worker_id: str
    ) -> None:
        job_id = uuid.UUID(str(command["job_id"]))
        correlation_id = uuid.UUID(str(command["correlation_id"]))
        operation_key = str(command["operation_key"])
        job = await session.scalar(select(ExtractionJob).where(ExtractionJob.id == job_id).with_for_update())
        if job is None or job.status in {JobStatus.BROWSER_INITIALIZING.value, JobStatus.CANCELLED.value}:
            return
        if job.status != JobStatus.QUEUED.value:
            raise InvalidTransition("Planning command cannot claim the current job state.")
        if job.cancel_requested_at:
            await self.transition(
                session,
                job_id=job_id,
                expected_state=JobStatus.QUEUED,
                target_state=JobStatus.CANCELLED,
                reason="Cancellation acknowledged before planning.",
                operation_key=operation_key,
                correlation_id=correlation_id,
            )
            return
        job.lease_owner, job.lease_expires_at = worker_id, utcnow() + timedelta(seconds=120)
        await self.transition(
            session,
            job_id=job_id,
            expected_state=JobStatus.QUEUED,
            target_state=JobStatus.PLANNING,
            reason="Planning placeholder started.",
            operation_key=operation_key,
            correlation_id=correlation_id,
        )
        session.add(
            ExtractionPlan(
                job_id=job_id,
                version=1,
                status="DRAFT",
                plan={
                    "version": 1,
                    "status": "DRAFT",
                    "source": {"type": "placeholder"},
                    "fields": [],
                    "steps": [],
                },
                model_name=None,
            )
        )
        await session.flush()
        await self.transition(
            session,
            job_id=job_id,
            expected_state=JobStatus.PLANNING,
            target_state=JobStatus.BROWSER_INITIALIZING,
            reason="Deterministic plan placeholder stored; browser work is blocked until Phase 3.",
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
        page.status = "CAPTURED"
        page.final_url = navigation.final_url
        page.http_status = navigation.status
        page.content_type = navigation.content_type
        page.title = navigation.title
        page.viewport = navigation.viewport
        page.navigation_time_ms = navigation.navigation_time_ms
        page.redirect_count = navigation.redirect_count
        page.browser_metadata = {"phase": 3, "event_count": len(result.events)}
        page.captured_at = utcnow()
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
            plan=PlanProjection(version=plan.version, status=plan.status) if plan else None,
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
            phase = "browser" if job.status == JobStatus.BROWSER_INITIALIZING.value else "planning"
            command_type = "run_browser_capture" if phase == "browser" else "run_planning"
            key = f"job:{job.id}:{phase}:{job.attempt}"
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
                    },
                )
            )
            recovered += 1
        return recovered
