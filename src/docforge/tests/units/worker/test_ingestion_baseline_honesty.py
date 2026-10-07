"""Finding D5 — IngestionFacade.index must NOT advance the indexed baseline (which clears
needs_reindex) while the Qdrant store lacks a semantic/lexical field's named vector: the field is not
searchable, and a reingest never adds the vector (only an index rebuild does)."""

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

from shared_libs.services.db.facades import IngestionFacade
from shared_libs.services.db.facades import ingestion_facade as facade_module
from shared_libs.services.db.qdrant import QdrantPoint


def _postgres() -> MagicMock:
    @asynccontextmanager
    async def _session():
        yield MagicMock()

    postgres = MagicMock()
    postgres.session = _session
    return postgres


def _wire(monkeypatch, missing: set[str]) -> AsyncMock:
    """Stub the store/PG calls of ``index``; return the CollectionApi.update spy."""
    monkeypatch.setattr(facade_module.CollectionApi, "get_schema", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        facade_module.QdrantCollectionApi, "ensure", AsyncMock(return_value=missing)
    )
    monkeypatch.setattr(facade_module.QdrantIndexApi, "delete_by_document", AsyncMock())
    monkeypatch.setattr(facade_module.QdrantIndexApi, "upsert", AsyncMock())
    monkeypatch.setattr(facade_module.ChunkApi, "mark_indexed", AsyncMock())
    collection = MagicMock(pipeline={})
    monkeypatch.setattr(facade_module.CollectionApi, "get", AsyncMock(return_value=collection))
    update = AsyncMock()
    monkeypatch.setattr(facade_module.CollectionApi, "update", update)
    return update


async def _index() -> None:
    facade = IngestionFacade(_postgres(), MagicMock(), MagicMock())
    points = [QdrantPoint(point_id=str(uuid.uuid4()), payload={})]
    await facade.index(uuid.uuid4(), uuid.uuid4(), dense_dim=8, points=points)


async def test_missing_vectors_keep_needs_reindex_and_the_old_baseline(monkeypatch) -> None:
    update = _wire(monkeypatch, missing={"title"})
    await _index()
    update.assert_awaited_once()
    kwargs = update.await_args.kwargs
    assert kwargs == {"needs_reindex": True}
    assert "indexed_signature" not in kwargs


async def test_aligned_store_advances_the_baseline_and_clears_the_flag(monkeypatch) -> None:
    update = _wire(monkeypatch, missing=set())
    await _index()
    kwargs = update.await_args.kwargs
    assert kwargs["needs_reindex"] is False
    assert isinstance(kwargs["indexed_signature"], str)
