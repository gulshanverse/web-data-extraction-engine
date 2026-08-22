"""Async SQLAlchemy session lifecycle. PostgreSQL is the source of truth for Phase 2."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from wde_api.config import get_settings

engine = create_async_engine(get_settings().database_url, pool_pre_ping=True, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session


async def dependency_ready() -> bool:
    from sqlalchemy import text

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
