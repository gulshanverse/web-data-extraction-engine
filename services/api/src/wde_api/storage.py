"""Provider-neutral local ArtifactStore adapter using opaque generated keys, atomic writes, checksums, and restricted filesystem permissions."""

from __future__ import annotations

import asyncio
import hashlib
import os
import secrets
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


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


class LocalArtifactStore:
    allowed_media_types = {
        "application/json",
        "application/octet-stream",
        "application/pdf",
        "image/jpeg",
        "image/png",
        "text/csv",
        "text/plain",
    }

    def __init__(self, root: Path, *, max_bytes: int = 100 * 1024 * 1024) -> None:
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
        if media_type not in self.allowed_media_types:
            raise StorageError("Unsupported artifact media type.")
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

    async def create_download_url(self, ref: ArtifactRef, *, expires_in: timedelta) -> str:
        del expires_in
        # Local development has no public download server; a future adapter returns authorized signed URLs.
        return f"local-artifact://{ref.key}"
