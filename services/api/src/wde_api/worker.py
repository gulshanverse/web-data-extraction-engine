"""Redis worker process. It executes only the durable planning placeholder and deliberately stops before Phase 3 browser work."""

from __future__ import annotations

import socket

from arq import Retry
from arq.cron import cron

from wde_api.database import SessionFactory
from wde_api.domain import RetryableOperationError, retry_delay_seconds
from wde_api.logging import configure_logging
from wde_api.queue import OutboxDispatcher, redis_settings
from wde_api.services import JobService


async def startup(_: dict) -> None:
    from wde_api.config import get_settings

    configure_logging(get_settings().log_level)


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


class WorkerSettings:
    functions = [run_planning]
    cron_jobs = [cron(recover_abandoned_work, second={0, 15, 30, 45})]
    on_startup = startup
    redis_settings = redis_settings()
    max_jobs = 10
    job_timeout = 120
    keep_result = 0


if __name__ == "__main__":
    from arq import run_worker

    run_worker(WorkerSettings)
