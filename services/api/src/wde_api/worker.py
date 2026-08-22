"""Redis worker process for durable planning and the existing Phase 3 browser capture boundary."""

from __future__ import annotations

import socket

import structlog
from arq import Retry
from arq.cron import cron

from wde_api.browser_engine import PlaywrightBrowserEngine
from wde_api.browser_errors import BrowserCancelled, BrowserEngineError
from wde_api.browser_policy import DefaultBrowserPolicy
from wde_api.browser_types import BrowserOperationRequest
from wde_api.database import SessionFactory
from wde_api.discovery_errors import (
    DiscoveryBrowserFailed,
    DiscoveryCancelled,
    DiscoveryError,
    DiscoveryNavigationFailed,
    DiscoveryPolicyBlocked,
    DiscoveryTimeout,
)
from wde_api.discovery_service import DiscoveryService
from wde_api.discovery_types import DiscoveryMethod
from wde_api.domain import retry_delay_seconds
from wde_api.extraction_errors import (
    ExtractionBrowserFailed,
    ExtractionCancelled,
    ExtractionError,
    ExtractionPolicyBlocked,
    ExtractionTimeout,
)
from wde_api.extraction_service import ExtractionService
from wde_api.extraction_types import ContentBlockSignal, ExtractionDocument, TableSignal
from wde_api.logging import configure_logging
from wde_api.planner_errors import PlannerError, PlannerUnavailable
from wde_api.planner_model import build_planner_model
from wde_api.planner_service import PlannerService
from wde_api.queue import OutboxDispatcher, redis_settings
from wde_api.services import JobService
from wde_api.validation_errors import ValidationEngineError, ValidationInfrastructureError
from wde_api.validation_service import ValidationService

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
    _["discovery_service"] = DiscoveryService(settings)
    _["extraction_service"] = ExtractionService(max_evidence_chars=settings.extraction_max_evidence_chars)
    _["validation_service"] = ValidationService()


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


def _discovery_error(error: BrowserEngineError) -> DiscoveryError:
    if isinstance(error, BrowserCancelled):
        return DiscoveryCancelled("Discovery navigation was cancelled safely.")
    if error.code in {"BROWSER_TIMEOUT", "NAVIGATION_TIMEOUT"}:
        return DiscoveryTimeout("Discovery navigation timed out.")
    if error.code in {
        "URL_POLICY_BLOCKED",
        "DOMAIN_NOT_ALLOWED",
        "REDIRECT_BLOCKED",
        "RESOURCE_LIMIT_EXCEEDED",
    }:
        return DiscoveryPolicyBlocked("Discovery navigation was blocked by the existing browser policy.")
    if error.code in {"NAVIGATION_FAILED", "PAGE_CRASHED"}:
        return DiscoveryNavigationFailed("Discovery navigation could not complete.")
    return DiscoveryBrowserFailed("Discovery browser operation failed.")


async def run_discovery(ctx: dict, command: dict[str, object]) -> None:
    service = JobService()
    discovery: DiscoveryService = ctx["discovery_service"]
    settings = discovery.settings
    async with SessionFactory() as session:
        async with session.begin():
            operation = await service.claim_discovery(
                session,
                command,
                worker_id=socket.gethostname(),
                lease_seconds=settings.worker_lease_seconds,
            )
    if operation is None:
        return
    log.info(
        "discovery.started",
        job_id=str(operation.job_id),
        correlation_id=str(operation.correlation_id),
        operation_key=operation.operation_key,
        page_id=str(operation.page_id),
    )
    request = BrowserOperationRequest(
        job_id=str(operation.job_id),
        project_id=str(operation.project_id),
        correlation_id=str(operation.correlation_id),
        operation_key=operation.operation_key,
        url=operation.page_url,
        allowed_domain=operation.source_domain,
        capture_screenshot=False,
        include_navigation_signals=operation.page_method != DiscoveryMethod.SITEMAP.value,
        navigation_signal_limit=settings.discovery_max_links_per_page,
        include_document_text=operation.page_method == DiscoveryMethod.SITEMAP.value,
        document_text_limit=settings.discovery_sitemap_max_bytes,
    )
    try:
        result = await ctx["browser_engine"].capture(request)
    except BrowserEngineError as browser_error:
        error = _discovery_error(browser_error)
        async with SessionFactory() as session:
            async with session.begin():
                retry_attempt = await service.fail_discovery(
                    session, command, error, max_attempts=settings.planner_max_retries
                )
        if retry_attempt is not None:
            raise Retry(defer=retry_delay_seconds(retry_attempt)) from browser_error
        return
    async with SessionFactory() as session:
        async with session.begin():
            await service.complete_discovery_page(session, command, operation, result, discovery=discovery)
    if settings.discovery_min_delay_seconds:
        import asyncio

        await asyncio.sleep(settings.discovery_min_delay_seconds)
    log.info(
        "discovery.completed",
        job_id=str(operation.job_id),
        correlation_id=str(operation.correlation_id),
        operation_key=operation.operation_key,
        page_id=str(operation.page_id),
    )


def _extraction_error(error: BrowserEngineError) -> ExtractionError:
    if isinstance(error, BrowserCancelled):
        return ExtractionCancelled("Extraction navigation was cancelled safely.")
    if error.code in {"BROWSER_TIMEOUT", "NAVIGATION_TIMEOUT"}:
        return ExtractionTimeout("Extraction navigation timed out.")
    if error.code in {
        "URL_POLICY_BLOCKED",
        "DOMAIN_NOT_ALLOWED",
        "REDIRECT_BLOCKED",
        "RESOURCE_LIMIT_EXCEEDED",
    }:
        return ExtractionPolicyBlocked("Extraction navigation was blocked by the existing browser policy.")
    return ExtractionBrowserFailed("Extraction browser operation failed.")


async def run_extraction(ctx: dict, command: dict[str, object]) -> None:
    service = JobService()
    extraction: ExtractionService = ctx["extraction_service"]
    from wde_api.config import get_settings

    settings = get_settings()
    async with SessionFactory() as session:
        async with session.begin():
            operation = await service.claim_extraction(
                session, command, worker_id=socket.gethostname(), lease_seconds=settings.worker_lease_seconds
            )
    if operation is None:
        return
    log.info(
        "extraction.started",
        job_id=str(operation.job_id),
        page_id=str(operation.page_id),
        operation_key=operation.operation_key,
    )
    request = BrowserOperationRequest(
        job_id=str(operation.job_id),
        project_id=str(operation.project_id),
        correlation_id=str(operation.correlation_id),
        operation_key=operation.operation_key,
        url=operation.page_url,
        allowed_domain=operation.source_domain,
        capture_screenshot=False,
        include_extraction_document=True,
        extraction_text_limit=settings.extraction_max_document_chars,
        extraction_item_limit=settings.extraction_max_document_items,
    )
    try:
        browser_result = await ctx["browser_engine"].capture(request)
    except BrowserEngineError as browser_error:
        error = _extraction_error(browser_error)
        async with SessionFactory() as session:
            async with session.begin():
                retry_attempt = await service.fail_extraction(
                    session, command, error, max_attempts=settings.extraction_max_retries
                )
        if retry_attempt is not None:
            raise Retry(defer=retry_delay_seconds(retry_attempt)) from browser_error
        return
    document = browser_result.extraction_document
    if document is None:
        error = ExtractionBrowserFailed("The browser did not return a bounded extraction document.")
        async with SessionFactory() as session:
            async with session.begin():
                await service.fail_extraction(
                    session, command, error, max_attempts=settings.extraction_max_retries
                )
        return
    result = extraction.extract(
        plan=operation.plan,
        page_url=browser_result.navigation.final_url,
        page_id=str(operation.page_id),
        document=ExtractionDocument(
            page_text=document.page_text,
            json_ld=document.json_ld,
            open_graph=document.open_graph,
            tables=tuple(TableSignal(item.headers, item.rows) for item in document.tables),
            blocks=tuple(
                ContentBlockSignal(item.tag, item.text, item.href, item.image_url) for item in document.blocks
            ),
            truncated=document.truncated,
        ),
    )
    async with SessionFactory() as session:
        async with session.begin():
            await service.complete_extraction_page(
                session, command, operation, result, server_max_records=settings.extraction_max_records
            )
    log.info(
        "extraction.completed",
        job_id=str(operation.job_id),
        page_id=str(operation.page_id),
        operation_key=operation.operation_key,
    )


async def run_validation(ctx: dict, command: dict[str, object]) -> None:
    service = JobService()
    validator: ValidationService = ctx["validation_service"]
    from wde_api.config import get_settings

    settings = get_settings()
    async with SessionFactory() as session:
        async with session.begin():
            operation = await service.claim_validation(
                session, command, worker_id=socket.gethostname(), lease_seconds=settings.worker_lease_seconds
            )
    if operation is None:
        return
    log.info(
        "validation.started",
        job_id=str(operation.job_id),
        operation_key=operation.operation_key,
        run_id=str(operation.validation_run_id),
    )
    try:
        async with SessionFactory() as session:
            async with session.begin():
                await service.complete_validation_run(session, operation, validator)
    except ValidationEngineError as error:
        async with SessionFactory() as session:
            async with session.begin():
                retry_attempt = await service.fail_validation(session, command, error, max_attempts=2)
        if retry_attempt is not None:
            raise Retry(defer=retry_delay_seconds(retry_attempt)) from error
    except Exception as exc:
        error = ValidationInfrastructureError("Validation infrastructure failed safely.")
        async with SessionFactory() as session:
            async with session.begin():
                retry_attempt = await service.fail_validation(session, command, error, max_attempts=2)
        if retry_attempt is not None:
            raise Retry(defer=retry_delay_seconds(retry_attempt)) from exc


class WorkerSettings:
    functions = [run_planning, run_browser_capture, run_discovery, run_extraction, run_validation]
    cron_jobs = [cron(recover_abandoned_work, second={0, 15, 30, 45})]
    on_startup = startup
    redis_settings = redis_settings()
    max_jobs = 10
    job_timeout = 120
    keep_result = 0


if __name__ == "__main__":
    from arq import run_worker

    run_worker(WorkerSettings)
