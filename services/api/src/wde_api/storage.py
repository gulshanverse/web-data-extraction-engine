"""Provider-neutral private artifact storage with opaque keys and bounded byte streams."""

from __future__ import annotations

import asyncio
import hashlib
import os
import secrets
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import httpx

from wde_api.config import Settings


class StorageError(Exception):
    pass


@dataclass(frozen=True)
class ArtifactRef:
    key: str
    artifact_type: str
    media_type: str
    byte_size: int
    checksum: str
    created_at: datetime
    expires_at: datetime | None


class ArtifactStore(Protocol):
    allowed_media_types: set[str]

    async def put(
        self,
        artifact_type: str,
        stream: AsyncIterator[bytes],
        *,
        media_type: str,
        metadata: Mapping[str, str],
        expires_at: datetime | None = None,
    ) -> ArtifactRef: ...

    async def open(self, ref: ArtifactRef) -> AsyncIterator[bytes]: ...
    async def head(self, ref: ArtifactRef) -> ArtifactRef: ...
    async def delete(self, ref: ArtifactRef) -> None: ...
    async def create_download_url(self, ref: ArtifactRef, *, expires_in: timedelta) -> str: ...


class BaseArtifactStore:
    allowed_media_types = {
        "application/json",
        "application/octet-stream",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "image/jpeg",
        "image/png",
        "text/csv",
        "text/html",
        "text/markdown",
        "text/plain",
    }

    def __init__(self, *, max_bytes: int) -> None:
        self.max_bytes = max_bytes

    def _validate_media_type(self, media_type: str) -> None:
        if media_type not in self.allowed_media_types:
            raise StorageError("Unsupported artifact media type.")

    async def create_download_url(self, ref: ArtifactRef, *, expires_in: timedelta) -> str:
        del ref, expires_in
        raise StorageError("Artifact download URLs are issued only by the authorized API endpoint.")


class LocalArtifactStore(BaseArtifactStore):
    """Development-only store. Production selection is fail-closed in Settings."""

    def __init__(self, root: Path, *, max_bytes: int = 100 * 1024 * 1024) -> None:
        super().__init__(max_bytes=max_bytes)
        self.root = root.resolve()
        self.max_bytes = max_bytes

    def _path(self, key: str) -> Path:
        if not key or "/" in key or "\\" in key or key in {".", ".."}:
            raise StorageError("Unsafe artifact key.")
        path = (self.root / key).resolve()
        if path.parent != self.root:
            raise StorageError("Unsafe artifact key.")
        return path

    async def put(
        self,
        artifact_type: str,
        stream: AsyncIterator[bytes],
        *,
        media_type: str,
        metadata: Mapping[str, str],
        expires_at: datetime | None = None,
    ) -> ArtifactRef:
        del metadata
        self._validate_media_type(media_type)
        await asyncio.to_thread(self.root.mkdir, parents=True, exist_ok=True, mode=0o700)
        key = secrets.token_urlsafe(24)
        destination = self._path(key)
        temporary = self._path(f".{key}.partial")
        digest = hashlib.sha256()
        size = 0
        try:
            with open(temporary, "xb", buffering=0) as handle:
                os.chmod(temporary, 0o600)
                async for chunk in stream:
                    if not isinstance(chunk, bytes):
                        raise StorageError("Artifact stream must yield bytes.")
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise StorageError("Artifact exceeds the configured size limit.")
                    digest.update(chunk)
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return ArtifactRef(
            key,
            artifact_type,
            media_type,
            size,
            f"sha256:{digest.hexdigest()}",
            datetime.now(UTC),
            expires_at,
        )

    async def open(self, ref: ArtifactRef) -> AsyncIterator[bytes]:
        path = self._path(ref.key)
        with open(path, "rb") as handle:
            while chunk := handle.read(64 * 1024):
                yield chunk

    async def head(self, ref: ArtifactRef) -> ArtifactRef:
        path = self._path(ref.key)
        if not path.exists():
            raise StorageError("Artifact not found.")
        return ref

    async def delete(self, ref: ArtifactRef) -> None:
        self._path(ref.key).unlink(missing_ok=True)


class SupabaseArtifactStore(BaseArtifactStore):
    """Server-only adapter for a private Supabase Storage bucket; it emits no public or signed URLs."""

    def __init__(
        self,
        *,
        supabase_url: str,
        service_role_key: str,
        bucket: str,
        max_bytes: int,
        timeout_seconds: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(max_bytes=max_bytes)
        self.base_url = supabase_url.rstrip("/")
        self.service_role_key = service_role_key
        self.bucket = bucket
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def _url(self, key: str) -> str:
        if not key or "/" in key or "\\" in key:
            raise StorageError("Unsafe artifact key.")
        return f"{self.base_url}/storage/v1/object/{quote(self.bucket, safe='')}/{quote(key, safe='')}"

    def _headers(self, media_type: str | None = None) -> dict[str, str]:
        headers = {"apikey": self.service_role_key, "Authorization": f"Bearer {self.service_role_key}"}
        if media_type:
            headers["Content-Type"] = media_type
        return headers

    async def _collect(self, stream: AsyncIterator[bytes]) -> tuple[bytes, str]:
        payload = bytearray()
        digest = hashlib.sha256()
        async for chunk in stream:
            if not isinstance(chunk, bytes):
                raise StorageError("Artifact stream must yield bytes.")
            payload.extend(chunk)
            if len(payload) > self.max_bytes:
                raise StorageError("Artifact exceeds the configured size limit.")
            digest.update(chunk)
        return bytes(payload), f"sha256:{digest.hexdigest()}"

    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        content: bytes | None = None,
    ) -> httpx.Response:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = await client.request(method, url, headers=headers, content=content)
        except httpx.HTTPError as exc:
            raise StorageError("Supabase Storage request failed.") from exc
        if response.status_code == 404:
            raise StorageError("Artifact not found.")
        if response.status_code >= 400:
            raise StorageError("Supabase Storage rejected the artifact operation.")
        return response

    async def put(
        self,
        artifact_type: str,
        stream: AsyncIterator[bytes],
        *,
        media_type: str,
        metadata: Mapping[str, str],
        expires_at: datetime | None = None,
    ) -> ArtifactRef:
        del metadata
        self._validate_media_type(media_type)
        payload, checksum = await self._collect(stream)
        key = secrets.token_urlsafe(24)
        headers = self._headers(media_type)
        headers["x-upsert"] = "false"
        await self._request("POST", self._url(key), headers=headers, content=payload)
        return ArtifactRef(key, artifact_type, media_type, len(payload), checksum, datetime.now(UTC), expires_at)

    async def open(self, ref: ArtifactRef) -> AsyncIterator[bytes]:
        response = await self._request("GET", self._url(ref.key), headers=self._headers())
        for start in range(0, len(response.content), 64 * 1024):
            yield response.content[start : start + 64 * 1024]

    async def head(self, ref: ArtifactRef) -> ArtifactRef:
        await self._request("HEAD", self._url(ref.key), headers=self._headers())
        return ref

    async def delete(self, ref: ArtifactRef) -> None:
        try:
            await self._request("DELETE", self._url(ref.key), headers=self._headers())
        except StorageError as exc:
            if str(exc) != "Artifact not found.":
                raise


def create_artifact_store(settings: Settings, *, max_bytes: int) -> ArtifactStore:
    """Select one store for API and worker; only explicit local profiles may write local bytes."""
    if settings.storage_provider == "supabase":
        return SupabaseArtifactStore(
            supabase_url=settings.supabase_url,
            service_role_key=settings.supabase_service_role_key,
            bucket=settings.supabase_storage_bucket,
            max_bytes=max_bytes,
            timeout_seconds=settings.supabase_request_timeout_seconds,
        )
    return LocalArtifactStore(settings.artifact_root, max_bytes=max_bytes)
