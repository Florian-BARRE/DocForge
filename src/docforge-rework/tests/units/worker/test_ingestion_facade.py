"""IngestionFacade — the worker's persistence path (dedup, blob storage, the one-transaction
save, vector indexing). Never exercised before (mocked away entirely in test_jobs_core.py); this
proves its ACTUAL ordering + derivation contracts. Postgres/Qdrant/S3 fully mocked, same
``_postgres_yielding``-style session stub as test_filter_sync_facade.py — no real store touched.
"""

import uuid
from contextlib import asynccontextmanager
from unittest.mock import ANY, AsyncMock, MagicMock

from shared_libs.public_models import FieldType
from shared_libs.services.db.facades import IngestionFacade, IngestionPayload
from shared_libs.services.db.facades import ingestion_facade as facade_module
from shared_libs.services.db.postgresql.tables import DocumentStatus
from shared_libs.services.db.qdrant import PayloadType, QdrantPoint


def _postgres_yielding(session: MagicMock) -> MagicMock:
    """A postgres mock whose session() is an async context manager yielding ``session``."""

    @asynccontextmanager
    async def _session():
        yield session

    postgres = MagicMock()
    postgres.session = _session
    return postgres


def _s3_yielding(client: MagicMock) -> MagicMock:
    """An s3 mock whose client() is an async context manager yielding ``client``."""

    @asynccontextmanager
    async def _client():
        yield client

    s3 = MagicMock()
    s3.client = _client
    s3.bucket = "docforge"
    return s3


def _tracking(calls: list[str], name: str, return_value: object = None):
    """An async stand-in that records its call order into ``calls`` before returning."""

    async def _fn(*args: object, **kwargs: object) -> object:
        calls.append(name)
        return return_value

    return _fn


# --------------------------------------------------------------------------- #
# find_duplicate
# --------------------------------------------------------------------------- #


async def test_find_duplicate_returns_the_matching_document(monkeypatch) -> None:
    existing = MagicMock()
    monkeypatch.setattr(facade_module.DocumentApi, "find", AsyncMock(return_value=existing))

    facade = IngestionFacade(_postgres_yielding(MagicMock()), MagicMock(), MagicMock())
    found = await facade.find_duplicate(uuid.uuid4(), "sha", "v1")

    assert found is existing


async def test_find_duplicate_returns_none_when_no_match(monkeypatch) -> None:
    monkeypatch.setattr(facade_module.DocumentApi, "find", AsyncMock(return_value=None))

    facade = IngestionFacade(_postgres_yielding(MagicMock()), MagicMock(), MagicMock())
    found = await facade.find_duplicate(uuid.uuid4(), "sha", "v1")

    assert found is None


# --------------------------------------------------------------------------- #
# save
# --------------------------------------------------------------------------- #


async def test_save_purges_chunks_and_ir_before_reinserting(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(facade_module.DocumentApi, "update_facts", _tracking(calls, "facts"))
    monkeypatch.setattr(facade_module.DocumentApi, "replace_pages", _tracking(calls, "pages"))
    monkeypatch.setattr(
        facade_module.DocumentApi, "replace_metadata", _tracking(calls, "doc_metadata")
    )
    monkeypatch.setattr(
        facade_module.ChunkApi, "delete_for_document", _tracking(calls, "chunk_delete")
    )
    monkeypatch.setattr(facade_module.IRApi, "delete_for_document", _tracking(calls, "ir_delete"))
    monkeypatch.setattr(facade_module.IRApi, "persist_ir", _tracking(calls, "ir_persist"))
    monkeypatch.setattr(
        facade_module.ChunkApi, "persist_chunks", _tracking(calls, "chunk_persist")
    )
    monkeypatch.setattr(facade_module.DocumentApi, "set_status", _tracking(calls, "set_status"))

    facade = IngestionFacade(_postgres_yielding(MagicMock()), MagicMock(), MagicMock())
    await facade.save(uuid.uuid4(), IngestionPayload())

    # 1. Purge-then-insert: both the chunk purge and the IR purge precede their re-insert.
    assert calls.index("chunk_delete") < calls.index("chunk_persist")
    assert calls.index("ir_delete") < calls.index("ir_persist")
    # 2. The persisted truth is only marked complete once everything else landed.
    assert calls[-1] == "set_status"


async def test_save_sets_status_done(monkeypatch) -> None:
    document_id = uuid.uuid4()
    monkeypatch.setattr(facade_module.DocumentApi, "update_facts", AsyncMock())
    monkeypatch.setattr(facade_module.DocumentApi, "replace_pages", AsyncMock())
    monkeypatch.setattr(facade_module.DocumentApi, "replace_metadata", AsyncMock())
    monkeypatch.setattr(facade_module.ChunkApi, "delete_for_document", AsyncMock())
    monkeypatch.setattr(facade_module.IRApi, "delete_for_document", AsyncMock())
    monkeypatch.setattr(facade_module.IRApi, "persist_ir", AsyncMock())
    monkeypatch.setattr(facade_module.ChunkApi, "persist_chunks", AsyncMock())
    set_status = AsyncMock()
    monkeypatch.setattr(facade_module.DocumentApi, "set_status", set_status)

    facade = IngestionFacade(_postgres_yielding(MagicMock()), MagicMock(), MagicMock())
    await facade.save(document_id, IngestionPayload())

    set_status.assert_awaited_once_with(ANY, document_id, DocumentStatus.DONE)


# --------------------------------------------------------------------------- #
# store_blobs
# --------------------------------------------------------------------------- #


async def test_store_blobs_writes_s3_before_the_registry(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(facade_module.S3ObjectApi, "put_many", _tracking(calls, "s3_put"))
    monkeypatch.setattr(facade_module.BlobApi, "register", _tracking(calls, "pg_register"))

    facade = IngestionFacade(
        _postgres_yielding(MagicMock()), MagicMock(), _s3_yielding(MagicMock())
    )
    await facade.store_blobs([MagicMock()], [MagicMock(), MagicMock()])

    # S3 bytes land before ANY registry row, so a mid-write crash never orphans a Postgres row.
    assert calls[0] == "s3_put"
    assert calls[1:] == ["pg_register", "pg_register"]


async def test_store_blobs_skips_s3_when_no_objects(monkeypatch) -> None:
    put_many = AsyncMock()
    register = AsyncMock()
    monkeypatch.setattr(facade_module.S3ObjectApi, "put_many", put_many)
    monkeypatch.setattr(facade_module.BlobApi, "register", register)

    facade = IngestionFacade(
        _postgres_yielding(MagicMock()), MagicMock(), _s3_yielding(MagicMock())
    )
    await facade.store_blobs([], [MagicMock()])

    put_many.assert_not_called()
    register.assert_awaited_once()


# --------------------------------------------------------------------------- #
# index
# --------------------------------------------------------------------------- #


def _field(name: str, field_type: FieldType, *, filterable=False, semantic=False, lexical=False):
    return MagicMock(
        field_name=name,
        field_type=field_type,
        filterable=filterable,
        semantic=semantic,
        lexical=lexical,
        enum_values=None,
    )


async def test_index_derives_vector_space_from_schema_and_marks_chunks_indexed(monkeypatch) -> None:
    collection_id = uuid.uuid4()
    schema = [
        _field("topic", FieldType.STRING, filterable=True, semantic=True),
        _field("year", FieldType.INTEGER, filterable=True),
        _field("body", FieldType.TEXT, lexical=True),
    ]
    monkeypatch.setattr(
        facade_module.CollectionApi, "get_schema", AsyncMock(return_value=schema)
    )
    ensure = AsyncMock()
    upsert = AsyncMock()
    mark_indexed = AsyncMock()
    monkeypatch.setattr(facade_module.QdrantCollectionApi, "ensure", ensure)
    monkeypatch.setattr(facade_module.QdrantIndexApi, "upsert", upsert)
    monkeypatch.setattr(facade_module.ChunkApi, "mark_indexed", mark_indexed)

    chunk_ids = [uuid.uuid4(), uuid.uuid4()]
    points = [QdrantPoint(point_id=str(cid), payload={}) for cid in chunk_ids]
    qdrant = MagicMock()

    facade = IngestionFacade(_postgres_yielding(MagicMock()), qdrant, MagicMock())
    await facade.index(collection_id, dense_dim=1024, points=points)

    # 1. The Qdrant collection is ensured from the schema's searchability flags.
    ensure.assert_awaited_once()
    ensure_kwargs = ensure.await_args.kwargs
    assert ensure.await_args.args[0] is qdrant.raw
    assert ensure_kwargs["dense_dim"] == 1024
    assert ensure_kwargs["semantic_fields"] == ["topic"]
    assert ensure_kwargs["lexical_fields"] == ["body"]
    assert ensure_kwargs["filterable_fields"] == {
        "topic": PayloadType.KEYWORD,
        "year": PayloadType.INTEGER,
    }
    assert ensure_kwargs["colbert_dim"] is None
    # 2. The points are upserted, then their chunks flagged indexed by parsed point ids.
    upsert.assert_awaited_once_with(qdrant.raw, ANY, points)
    mark_indexed.assert_awaited_once()
    marked_ids = mark_indexed.await_args.args[1]
    assert set(marked_ids) == set(chunk_ids)


async def test_index_threads_colbert_dim_when_given(monkeypatch) -> None:
    collection_id = uuid.uuid4()
    monkeypatch.setattr(facade_module.CollectionApi, "get_schema", AsyncMock(return_value=[]))
    ensure = AsyncMock()
    monkeypatch.setattr(facade_module.QdrantCollectionApi, "ensure", ensure)
    monkeypatch.setattr(facade_module.QdrantIndexApi, "upsert", AsyncMock())
    monkeypatch.setattr(facade_module.ChunkApi, "mark_indexed", AsyncMock())

    facade = IngestionFacade(_postgres_yielding(MagicMock()), MagicMock(), MagicMock())
    await facade.index(collection_id, dense_dim=1024, points=[], colbert_dim=128)

    assert ensure.await_args.kwargs["colbert_dim"] == 128
