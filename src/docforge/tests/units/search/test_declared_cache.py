"""DeclaredVectorsCache — one store read per collection per TTL; an expired entry is re-read."""

import uuid
from unittest.mock import AsyncMock

from shared_libs.services.db.qdrant import DeclaredVectors


async def test_reads_once_within_the_ttl_then_again_after_expiry(monkeypatch) -> None:
    from backend.libs.search import declared_cache  # noqa: PLC0415

    clock = [100.0]
    monkeypatch.setattr(declared_cache.time, "monotonic", lambda: clock[0])
    loader = AsyncMock(return_value=DeclaredVectors(dense=frozenset({"content_dense"})))
    cache = declared_cache.DeclaredVectorsCache(ttl_seconds=30)
    collection_id = uuid.uuid4()

    await cache.get(collection_id, loader)
    clock[0] += 29
    await cache.get(collection_id, loader)
    assert loader.await_count == 1

    clock[0] += 2
    assert (await cache.get(collection_id, loader)).dense == {"content_dense"}
    assert loader.await_count == 2
    # Another collection is its own entry.
    await cache.get(uuid.uuid4(), loader)
    assert loader.await_count == 3


async def test_a_failed_store_read_is_none_and_not_cached() -> None:
    from backend.libs.search import declared_cache  # noqa: PLC0415

    loader = AsyncMock(side_effect=[ConnectionError("qdrant down"), DeclaredVectors()])
    cache = declared_cache.DeclaredVectorsCache(ttl_seconds=30)
    collection_id = uuid.uuid4()

    assert await cache.get(collection_id, loader) is None
    assert await cache.get(collection_id, loader) == DeclaredVectors()
    assert loader.await_count == 2
