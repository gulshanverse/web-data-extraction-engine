"""Identity boundary: development headers are isolated from Supabase-backed production identity."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

import httpx
import jwt
from itsdangerous import BadData, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wde_api.config import Settings, get_settings
from wde_api.domain import DomainError
from wde_api.models import User


class NotAuthorized(DomainError):
    code = "NOT_AUTHORIZED"
    status_code = 403


class AuthenticationRequired(DomainError):
    code = "AUTHENTICATION_REQUIRED"
    status_code = 401


class SupabaseJwtVerifier:
    """Validates asymmetric Supabase access tokens using the project's JWKS endpoint."""

    supported_algorithms = {"RS256", "ES256", "EdDSA"}

    def __init__(self, settings: Settings, jwks_fetcher: Callable[[], Awaitable[dict[str, Any]]] | None = None) -> None:
        self.settings = settings
        self._jwks_fetcher = jwks_fetcher or self._fetch_jwks
        self._jwks: dict[str, Any] | None = None
        self._jwks_expires_at = datetime.min.replace(tzinfo=UTC)
        self._lock = asyncio.Lock()

    async def _fetch_jwks(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.settings.supabase_request_timeout_seconds) as client:
                response = await client.get(self.settings.supabase_jwks_url)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AuthenticationRequired("Identity verification is temporarily unavailable.") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list):
            raise AuthenticationRequired("Identity verification keys are unavailable.")
        return payload

    async def _get_jwks(self) -> dict[str, Any]:
        if self._jwks and datetime.now(UTC) < self._jwks_expires_at:
            return self._jwks
        async with self._lock:
            if self._jwks and datetime.now(UTC) < self._jwks_expires_at:
                return self._jwks
            self._jwks = await self._jwks_fetcher()
            self._jwks_expires_at = datetime.now(UTC) + timedelta(seconds=self.settings.supabase_jwks_cache_seconds)
            return self._jwks

    async def verify(self, token: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            key_id = header.get("kid")
        except jwt.PyJWTError as exc:
            raise AuthenticationRequired("The access token is invalid.") from exc
        if algorithm not in self.supported_algorithms or not isinstance(key_id, str):
            raise AuthenticationRequired("The access token uses an unsupported signing key.")
        jwks = await self._get_jwks()
        candidate = next((key for key in jwks["keys"] if key.get("kid") == key_id), None)
        if candidate is None:
            self._jwks = None
            jwks = await self._get_jwks()
            candidate = next((key for key in jwks["keys"] if key.get("kid") == key_id), None)
        if candidate is None:
            raise AuthenticationRequired("The access token signing key is unknown.")
        try:
            signing_key = jwt.PyJWK.from_dict(candidate).key
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=[algorithm],
                audience=self.settings.supabase_jwt_audience,
                issuer=f"{self.settings.supabase_url.rstrip('/')}/auth/v1",
                options={"require": ["exp", "sub", "iss", "aud"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationRequired("The access token could not be verified.") from exc
        if claims.get("role") != "authenticated":
            raise AuthenticationRequired("The access token is not a user session.")
        return claims


@lru_cache
def get_supabase_jwt_verifier() -> SupabaseJwtVerifier:
    return SupabaseJwtVerifier(get_settings())


async def resolve_development_principal(session: AsyncSession, x_dev_principal: str | None = None) -> User:
    settings = get_settings()
    if settings.app_env != "development":
        raise AuthenticationRequired("Authentication is required for this environment.")
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


async def resolve_supabase_principal(session: AsyncSession, claims: dict[str, Any]) -> User:
    subject, email = claims.get("sub"), claims.get("email")
    if not isinstance(subject, str) or not subject or len(subject) > 255:
        raise AuthenticationRequired("The access token does not identify a user.")
    if not isinstance(email, str) or "@" not in email or len(email) > 320:
        raise AuthenticationRequired("An email-backed Supabase user is required.")
    email = email.strip().lower()
    user = await session.scalar(select(User).where(User.auth_subject == subject))
    if user is not None:
        if user.email != email:
            user.email = email
        return user
    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        if existing.auth_subject and existing.auth_subject != subject:
            raise NotAuthorized("This email is already associated with a different identity.")
        existing.auth_subject = subject
        return existing
    user = User(email=email, auth_subject=subject)
    session.add(user)
    await session.flush()
    return user


async def resolve_principal(session: AsyncSession, *, authorization: str | None, x_dev_principal: str | None = None) -> User:
    settings = get_settings()
    if settings.app_env == "development":
        return await resolve_development_principal(session, x_dev_principal)
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationRequired("A bearer access token is required.")
    claims = await get_supabase_jwt_verifier().verify(authorization.removeprefix("Bearer ").strip())
    return await resolve_supabase_principal(session, claims)


def session_serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.app_session_secret, salt="wde-api-session-v1")


def issue_session_cookie(user: User, settings: Settings) -> str:
    return session_serializer(settings).dumps({"sub": user.auth_subject, "uid": str(user.id)})


async def resolve_session_cookie(session: AsyncSession, value: str | None) -> User:
    settings = get_settings()
    if not value or settings.app_env == "development":
        raise AuthenticationRequired("A verified API session is required.")
    try:
        payload = session_serializer(settings).loads(value, max_age=settings.auth_session_max_age_seconds)
    except (BadData, SignatureExpired) as exc:
        raise AuthenticationRequired("The API session has expired.") from exc
    subject = payload.get("sub") if isinstance(payload, dict) else None
    if not isinstance(subject, str):
        raise AuthenticationRequired("The API session is invalid.")
    user = await session.scalar(select(User).where(User.auth_subject == subject))
    if user is None:
        raise AuthenticationRequired("The API session user is unavailable.")
    return user
