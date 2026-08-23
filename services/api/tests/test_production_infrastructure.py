from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import ValidationError
from wde_api.auth import SupabaseJwtVerifier
from wde_api.config import Settings
from wde_api.storage import StorageError, SupabaseArtifactStore


async def chunks(*values: bytes) -> AsyncIterator[bytes]:
    for value in values:
        yield value


def production_settings(**overrides: str) -> Settings:
    values = {
        "app_env": "production",
        "app_url": "https://app.example.invalid",
        "api_url": "https://api.example.invalid",
        "trusted_hosts": "api.example.invalid",
        "app_session_secret": "test-session-secret-not-for-production",
        "database_url": "postgresql+asyncpg://postgres:password@aws-region.pooler.supabase.com:5432/postgres?ssl=require",
        "redis_url": "rediss://:password@redis.example.invalid:6379/0",
        "storage_provider": "supabase",
        "supabase_url": "https://project.example.invalid",
        "supabase_anon_key": "test-publishable-key",
        "supabase_service_role_key": "test-service-role-key",
        "supabase_storage_bucket": "generated-artifacts",
        "cors_allowed_origins": "https://app.example.invalid",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_production_settings_fail_closed_for_local_or_wildcard_values() -> None:
    with pytest.raises(ValidationError, match="STORAGE_PROVIDER"):
        production_settings(storage_provider="local")
    with pytest.raises(ValidationError, match="rediss"):
        production_settings(redis_url="redis://localhost:6379/0")
    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS"):
        production_settings(cors_allowed_origins="*")
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        production_settings(database_url="postgresql+asyncpg://wde:wde@localhost:5432/wde?ssl=require")


@pytest.mark.asyncio
async def test_asymmetric_supabase_jwt_requires_expected_claims() -> None:
    settings = production_settings()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    public_jwk.update({"kid": "key-1", "alg": "RS256", "use": "sig"})

    async def jwks() -> dict[str, object]:
        return {"keys": [public_jwk]}

    token = jwt.encode(
        {
            "iss": "https://project.example.invalid/auth/v1",
            "aud": "authenticated",
            "sub": "supabase-user-id",
            "email": "person@example.invalid",
            "role": "authenticated",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "key-1"},
    )
    assert (await SupabaseJwtVerifier(settings, jwks).verify(token))["sub"] == "supabase-user-id"


@pytest.mark.asyncio
async def test_supabase_storage_uses_private_server_only_requests_and_bounds_payloads() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, content=b"artifact", request=request)
        return httpx.Response(200, request=request)

    store = SupabaseArtifactStore(
        supabase_url="https://project.example.invalid",
        service_role_key="server-only-key",
        bucket="generated-artifacts",
        max_bytes=16,
        transport=httpx.MockTransport(handler),
    )
    reference = await store.put("generated_export", chunks(b"arti", b"fact"), media_type="text/plain", metadata={})
    assert reference.key and "/" not in reference.key
    assert b"".join([part async for part in store.open(reference)]) == b"artifact"
    await store.delete(reference)
    assert [request.method for request in requests] == ["POST", "GET", "DELETE"]
    assert all(request.headers["authorization"] == "Bearer server-only-key" for request in requests)
    with pytest.raises(StorageError, match="Unsupported"):
        await store.put("generated_export", chunks(b"x"), media_type="image/gif", metadata={})
    with pytest.raises(StorageError, match="size limit"):
        await store.put("generated_export", chunks(b"x" * 17), media_type="text/plain", metadata={})
