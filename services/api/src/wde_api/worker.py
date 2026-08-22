"""Redis worker process for durable planning and the existing Phase 3 browser capture boundary."""

from __future__ import annotations

import socket

import structlog
from arq import Retry
from arq.cron import cron

from wde_api.browser_engine import PlaywrightBrowserEngine
from wde_api.browser_errors import BrowserEngineError
from wde_api.browser_policy import DefaultBrowserPolicy
from wde_api.browser_types import BrowserOperationRequest
from wde_api.database import SessionFactory
from wde_api.domain import retry_delay_seconds
from wde_api.logging import configure_logging
from wde_api.planner_errors import PlannerError, PlannerUnavailable
from wde_api.planner_model import build_planner_model
from wde_api.planner_service import PlannerService
from wde_api.queue import OutboxDispatcher, redis_settings
from wde_api.services import JobService

log = structlog.get_logger()


async def startup(_: dict) -> None:
    from wde_api.config import get_settings

    settings = get_settings()
    configure_logging(settings.log_level)

    async def cancellation_probe(job_id: str) -> bool:
        import uuid

        from wde_api.models import ExtractionJob

        async with SessionFactory() as session:
            job = await session.get(ExtractionJob, uuid.UUID(job_id))
            return bool(job and (job.cancel_requested_at or job.status == "CANCELLED"))

    def policy_factory(request: BrowserOperationRequest) -> DefaultBrowserPolicy:
        return DefaultBrowserPolicy(
            allowed_domain=request.allowed_domain,
            max_pages=settings.browser_max_pages,
            max_redirects=settings.browser_max_redirects,
            cancellation_probe=cancellation_probe,
        )

    _["browser_engine"] = PlaywrightBrowserEngine.from_settings(settings, policy_factory)
    _["planner_service"] = PlannerService(build_planner_model(settings), settings)


async def recover_abandoned_work(_: dict) -> None:
    service = JobService()
    async with SessionFactory() as session:
        async with session.begin():
            await service.recover_expired_leases(session)
            await OutboxDispatcher().dispatch_pending(session)


async def run_planning(ctx: dict, command: dict[str, object]) -> None:
    service = JobService()
    planner = ctx["planner_service"]
    settings = planner.settings
    async with SessionFactory() as session:
        async with session.begin():
            operation = await service.claim_planning(
                session,
                command,
                worker_id=socket.gethostname(),
                lease_seconds=settings.worker_lease_seconds,
            )
    if operation is None:
        return
    log.info(
        "planner.started",
        job_id=str(operation.job_id),
        correlation_id=str(operation.correlation_id),
        operation_key=operation.operation_key,
        version=1,
    )
    try:
        log.info(
            "planner.requested",
            job_id=str(operation.job_id),
            correlation_id=str(operation.correlation_id),
            operation_key=operation.operation_key,
            version=1,
        )
        plan = await planner.create_plan(
            source_url=operation.source_url,
            task=operation.task,
            requested_fields=operation.requested_fields,
            options=operation.options,
            outputs=operation.output_formats,
        )
    except PlannerError as error:
        if error.code in {"PLANNER_SCHEMA_ERROR", "PLANNER_INVALID_OUTPUT", "PLANNER_POLICY_REJECTED"}:
            log.warning(
                "planner.validation_failed",
                job_id=str(operation.job_id),
                correlation_id=str(operation.correlation_id),
                operation_key=operation.operation_key,
                version=1,
                code=error.code,
            )
        else:
            log.warning(
                "planner.failed",
                job_id=str(operation.job_id),
                correlation_id=str(operation.correlation_id),
                operation_key=operation.operation_key,
                version=1,
                code=error.code,
            )
        async with SessionFactory() as session:
            async with session.begin():
                retry_attempt = await service.fail_planning(
                    session, command, error, max_retries=settings.planner_max_retries
                )
        if retry_attempt is not None:
            log.info(
                "planner.retry",
                job_id=str(operation.job_id),
                correlation_id=str(operation.correlation_id),
                operation_key=operation.operation_key,
                version=1,
                code=error.code,
            )
            raise Retry(defer=retry_delay_seconds(retry_attempt)) from error
        return
    except Exception as exc:
        error = PlannerUnavailable("Planner operation failed safely.")
        log.warning(
            "planner.failed",
            job_id=str(operation.job_id),
            correlation_id=str(operation.correlation_id),
            operation_key=operation.operation_key,
            version=1,
            code=error.code,
        )
        async with SessionFactory() as session:
            async with session.begin():
                retry_attempt = await service.fail_planning(
                    session, command, error, max_retries=settings.planner_max_retries
                )
        if retry_attempt is not None:
            raise Retry(defer=retry_delay_seconds(retry_attempt)) from exc
        return
    async with SessionFactory() as session:
        async with session.begin():
            completed = await service.complete_planning(
                session,
                command,
                plan,
                provider_name=planner.model.provider_name,
                model_name=planner.model.model_name,
            )
    if completed:
        log.info(
            "planner.completed",
            job_id=str(operation.job_id),
            correlation_id=str(operation.correlation_id),
            operation_key=operation.operation_key,
            version=plan.plan_version,
        )


async def run_browser_capture(ctx: dict, command: dict[str, object]) -> None:
    service = JobService()
    async with SessionFactory() as session:
        async with session.begin():
            request = await service.prepare_browser_capture(session, command, worker_id=socket.gethostname())
    if request is None:
        return
    try:
        result = await ctx["browser_engine"].capture(request)
    except BrowserEngineError as error:
        async with SessionFactory() as session:
            async with session.begin():
                should_retry = await service.fail_browser_capture(session, command, error)
        if should_retry:
            raise Retry(defer=retry_delay_seconds(int(command.get("attempt", 1)))) from error
        return
    async with SessionFactory() as session:
        async with session.begin():
            await service.complete_browser_capture(session, command, result)


class WorkerSettings:
    functions = [run_planning, run_browser_capture]
    cron_jobs = [cron(recover_abandoned_work, second={0, 15, 30, 45})]
    on_startup = startup
    redis_settings = redis_settings()
    max_jobs = 10
    job_timeout = 120
    keep_result = 0


if __name__ == "__main__":
    from arq import run_worker

    run_worker(WorkerSettings)
