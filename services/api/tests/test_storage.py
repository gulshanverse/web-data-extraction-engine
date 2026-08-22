from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from wde_api.storage import LocalArtifactStore, StorageError


async def chunks(*values: bytes) -> AsyncIterator[bytes]:
    for value in values:
        yield value


@pytest.mark.asyncio
async def test_round_trip_checksum_size_and_idempotent_delete(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    ref = await store.put("temporary", chunks(b"hello", b" world"), media_type="text/plain", metadata={})
    assert ref.byte_size == 11
    assert ref.checksum == "sha256:b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
    assert b"".join([chunk async for chunk in store.open(ref)]) == b"hello world"
    await store.delete(ref)
    await store.delete(ref)


@pytest.mark.asyncio
async def test_rejects_path_traversal_media_types_and_oversized_streams(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path, max_bytes=4)
    with pytest.raises(StorageError):
        await store.put("temporary", chunks(b"x"), media_type="image/gif", metadata={})
    with pytest.raises(StorageError):
        await store.put("temporary", chunks(b"12345"), media_type="text/plain", metadata={})
    with pytest.raises(StorageError):
        store._path("../outside")
    assert not list(tmp_path.glob("*.partial"))
