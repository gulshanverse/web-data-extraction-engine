"""Redis worker process. It executes only the durable planning placeholder and deliberately stops before Phase 3 browser work."""

from __future__ import annotations

import socket

from arq import Retry
from arq.cron import cron

from wde_api.browser_engine import PlaywrightBrowserEngine
from wde_api.browser_errors import BrowserEngineError
from wde_api.browser_policy import DefaultBrowserPolicy
from wde_api.browser_types import BrowserOperationRequest
from wde_api.database import SessionFactory
from wde_api.domain import RetryableOperationError, retry_delay_seconds
from wde_api.logging import configure_logging
from wde_api.queue import OutboxDispatcher, redis_settings
from wde_api.services import JobService


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


async def recover_abandoned_work(_: dict) -> None:
    service = JobService()
    async with SessionFactory() as session:
        async with session.begin():
            await service.recover_expired_leases(session)
            await OutboxDispatcher().dispatch_pending(session)


async def run_planning(_: dict, command: dict[str, object]) -> None:
    service = JobService()
    try:
        async with SessionFactory() as session:
            async with session.begin():
                await service.process_planning_placeholder(session, command, worker_id=socket.gethostname())
    except RetryableOperationError as error:
        raise Retry(defer=retry_delay_seconds(int(command.get("attempt", 1)))) from error


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
