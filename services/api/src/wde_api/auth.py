"""Development-only identity boundary. It is explicit local scaffolding, not production authentication."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wde_api.config import get_settings
from wde_api.domain import DomainError
from wde_api.models import User


class NotAuthorized(DomainError):
    code = "NOT_AUTHORIZED"
    status_code = 403


async def resolve_development_principal(
    session: AsyncSession,
    x_dev_principal: str | None = None,
) -> User:
    settings = get_settings()
    if settings.app_env != "development":
        raise NotAuthorized("Authentication is required for this environment.")
    email = (x_dev_principal or settings.dev_principal_email).strip().lower()
    if not email or "@" not in email or len(email) > 320:
        raise NotAuthorized("The development identity is invalid.")
    user = await session.scalar(select(User).where(User.email == email))
    if user:
        return user
    user = User(email=email)
    session.add(user)
    await session.flush()
    return user
