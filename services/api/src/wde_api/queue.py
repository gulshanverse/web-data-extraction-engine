"""Redis transport adapter. PostgreSQL outbox and job state stay authoritative."""

from __future__ import annotations

from datetime import UTC, datetime

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wde_api.config import get_settings
from wde_api.models import WorkOutbox


def redis_settings() -> RedisSettings:
    from urllib.parse import urlsplit

    parsed = urlsplit(get_settings().redis_url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=int((parsed.path or "/0").lstrip("/") or 0),
    )


class OutboxDispatcher:
    async def dispatch_pending(self, session: AsyncSession, *, limit: int = 50) -> int:
        now = datetime.now(UTC)
        pending = (
            await session.scalars(
                select(WorkOutbox)
                .where(WorkOutbox.published_at.is_(None), WorkOutbox.available_at <= now)
                .order_by(WorkOutbox.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
        if not pending:
            return 0
        pool = await create_pool(redis_settings())
        published = 0
        try:
            for item in pending:
                await pool.enqueue_job(item.command_type, item.payload, _job_id=item.operation_key)
                item.published_at = now
                published += 1
        finally:
            await pool.aclose()
        return published


async def redis_ready() -> bool:
    try:
        pool = await create_pool(redis_settings())
        try:
            return bool(await pool.ping())
        finally:
            await pool.aclose()
    except Exception:
        return False
