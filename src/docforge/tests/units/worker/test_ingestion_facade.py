"""IngestionFacade — the worker's persistence path (dedup, blob storage, the one-transaction
save, vector indexing). Never exercised before (mocked away entirely in test_jobs_core.py); this
proves its ACTUAL ordering + derivation contracts. Postgres/Qdrant/S3 fully mocked, same
``_postgres_yielding``-style session stub as test_filter_sync_facade.py — no real store touched.
"""

import uuid
from contextlib import asynccontextmanager
from unittest.mock import ANY, AsyncMock, MagicMock

from shared_libs.public_models import FieldType
from shared_libs.services.db.facades import IngestionFacade, IngestionPayload, ReingestOutcome
from shared_libs.services.db.facades import ingestion_facade as facade_module
from shared_libs.services.db.qdrant import PayloadType, QdrantPoint


def _postgres_yielding(session: MagicMock) -> MagicMock:
    """A postgres mock whose session() is an async context manager yielding ``session``."""

    @asynccontextmanager
    async def _session():
        yield session

    postgres = MagicMock()
    postgres.session = _session
    return postgres


def _session_with_flush() -> MagicMock:
    """A session mock whose ``flush`` is awaitable (``save`` flushes before the blob purge)."""
    session = MagicMock()
    session.flush = AsyncMock()
    return session


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


def _patch_save_apis(monkeypatch, calls: list[str]) -> None:
    """Patch every data-access call ``save`` makes as an order-recording stand-in."""
    monkeypatch.setattr(
        facade_module.BlobApi, "collect_hashes_for_document", _tracking(calls, "collect", [])
    )
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
    monkeypatch.setattr(facade_module.ChunkApi, "persist_chunks", _tracking(calls, "chunk_persist"))
    monkeypatch.setattr(
        facade_module.DocumentApi, "finalize_done", _tracking(calls, "finalize_done")
    )
    monkeypatch.setattr(
        facade_module.BlobApi, "delete_unreferenced", _tracking(calls, "blob_purge", [])
    )


async def test_save_purges_chunks_and_ir_before_reinserting(monkeypatch) -> None:
    calls: list[str] = []
    _patch_save_apis(monkeypatch, calls)

    facade = IngestionFacade(
        _postgres_yielding(_session_with_flush()), MagicMock(), _s3_yielding(MagicMock())
    )
    await facade.save(uuid.uuid4(), IngestionPayload())

    # 1. The supersede snapshot is taken FIRST, before any purge writes the fresh hashes.
    assert calls[0] == "collect"
    assert calls.index("collect") < calls.index("chunk_delete")
    # 2. Purge-then-insert: both the chunk purge and the IR purge precede their re-insert.
    assert calls.index("chunk_delete") < calls.index("chunk_persist")
    assert calls.index("ir_delete") < calls.index("ir_persist")
    # 3. The persisted truth is marked complete, THEN the now-orphaned old blobs are purged (last).
    assert calls.index("finalize_done") < calls.index("blob_purge")
    assert calls[-1] == "blob_purge"


async def test_save_sets_status_done(monkeypatch) -> None:
    document_id = uuid.uuid4()
    _patch_save_apis(monkeypatch, [])
    finalize_done = AsyncMock()
    monkeypatch.setattr(facade_module.DocumentApi, "finalize_done", finalize_done)

    facade = IngestionFacade(
        _postgres_yielding(_session_with_flush()), MagicMock(), _s3_yielding(MagicMock())
    )
    await facade.save(document_id, IngestionPayload())

    finalize_done.assert_awaited_once_with(ANY, document_id)


async def test_save_purges_superseded_blobs_but_keeps_shared_ones(monkeypatch) -> None:
    """A re-ingest whose renders/crops/PDF changed byte-wise must reclaim the OLD blobs — but only
    those nothing references anymore. The snapshot is taken before the purge; the guarded delete
    returns exactly the removed hashes; only those are deleted from S3 (the source hash survives)."""
    document_id = uuid.uuid4()
    _patch_save_apis(monkeypatch, [])
    # BEFORE the purge, the document referenced an old render + its source bytes.
    collect = AsyncMock(return_value=["old_render", "source_hash"])
    monkeypatch.setattr(facade_module.BlobApi, "collect_hashes_for_document", collect)
    # The guarded delete keeps the still-referenced source and removes only the superseded render.
    delete_unreferenced = AsyncMock(return_value=["old_render"])
    monkeypatch.setattr(facade_module.BlobApi, "delete_unreferenced", delete_unreferenced)
    s3_delete = AsyncMock()
    monkeypatch.setattr(facade_module.S3ObjectApi, "delete_many", s3_delete)

    facade = IngestionFacade(
        _postgres_yielding(_session_with_flush()), MagicMock(), _s3_yielding(MagicMock())
    )
    await facade.save(document_id, IngestionPayload())

    # The candidate snapshot (both hashes) is handed to the guarded, reference-re-checking delete.
    assert delete_unreferenced.await_args.args[1] == ["old_render", "source_hash"]
    # Only the hash actually removed (the superseded render) is deleted from S3 — the source survives.
    s3_delete.assert_awaited_once()
    assert s3_delete.await_args.args[2] == ["old_render"]


async def test_save_skips_s3_when_no_blobs_superseded(monkeypatch) -> None:
    """A first ingest (or a re-ingest whose blobs are byte-identical) purges nothing — no S3 call."""
    _patch_save_apis(monkeypatch, [])
    s3_delete = AsyncMock()
    monkeypatch.setattr(facade_module.S3ObjectApi, "delete_many", s3_delete)

    facade = IngestionFacade(
        _postgres_yielding(_session_with_flush()), MagicMock(), _s3_yielding(MagicMock())
    )
    await facade.save(uuid.uuid4(), IngestionPayload())

    s3_delete.assert_not_called()


# --------------------------------------------------------------------------- #
# store_blobs
# --------------------------------------------------------------------------- #


async def test_store_blobs_writes_s3_before_the_registry(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(facade_module.S3ObjectApi, "put_many", _tracking(calls, "s3_put"))
    monkeypatch.setattr(facade_module.BlobApi, "register_many", _tracking(calls, "pg_register"))

    facade = IngestionFacade(
        _postgres_yielding(MagicMock()), MagicMock(), _s3_yielding(MagicMock())
    )
    await facade.store_blobs([MagicMock()], [MagicMock(), MagicMock()])

    # S3 bytes land before the registry rows (one bulk insert), so a mid-write crash never orphans
    # a Postgres row.
    assert calls == ["s3_put", "pg_register"]


async def test_store_blobs_skips_s3_when_no_objects(monkeypatch) -> None:
    put_many = AsyncMock()
    register_many = AsyncMock()
    monkeypatch.setattr(facade_module.S3ObjectApi, "put_many", put_many)
    monkeypatch.setattr(facade_module.BlobApi, "register_many", register_many)

    facade = IngestionFacade(
        _postgres_yielding(MagicMock()), MagicMock(), _s3_yielding(MagicMock())
    )
    await facade.store_blobs([], [MagicMock()])

    put_many.assert_not_called()
    register_many.assert_awaited_once()


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
    monkeypatch.setattr(facade_module.CollectionApi, "get_schema", AsyncMock(return_value=schema))
    ensure = AsyncMock()
    delete_by_document = AsyncMock()
    upsert = AsyncMock()
    mark_indexed = AsyncMock()
    monkeypatch.setattr(facade_module.QdrantCollectionApi, "ensure", ensure)
    monkeypatch.setattr(facade_module.QdrantIndexApi, "delete_by_document", delete_by_document)
    monkeypatch.setattr(facade_module.QdrantIndexApi, "upsert", upsert)
    monkeypatch.setattr(facade_module.ChunkApi, "mark_indexed", mark_indexed)

    document_id = uuid.uuid4()
    chunk_ids = [uuid.uuid4(), uuid.uuid4()]
    points = [QdrantPoint(point_id=str(cid), payload={}) for cid in chunk_ids]
    qdrant = MagicMock()

    facade = IngestionFacade(_postgres_yielding(MagicMock()), qdrant, MagicMock())
    await facade.index(collection_id, document_id, dense_dim=1024, points=points)

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
    # 2. The document's stale points are purged (scoped to this one document) before the upsert.
    delete_by_document.assert_awaited_once_with(qdrant.raw, ANY, document_id)
    # 3. The points are upserted, then their chunks flagged indexed by parsed point ids.
    upsert.assert_awaited_once_with(qdrant.raw, ANY, points)
    mark_indexed.assert_awaited_once()
    marked_ids = mark_indexed.await_args.args[1]
    assert set(marked_ids) == set(chunk_ids)


async def test_index_deletes_document_points_before_upsert_so_reingest_never_orphans(
    monkeypatch,
) -> None:
    """A re-ingest mints fresh chunk ids, so the facade must delete the document's OLD points BEFORE
    upserting the new ones — otherwise the previous run's points survive with a live document_id +
    enabled payload and pollute the candidate pool. Prove the delete-then-upsert ordering."""
    collection_id = uuid.uuid4()
    document_id = uuid.uuid4()
    monkeypatch.setattr(facade_module.CollectionApi, "get_schema", AsyncMock(return_value=[]))
    monkeypatch.setattr(facade_module.QdrantCollectionApi, "ensure", AsyncMock())
    monkeypatch.setattr(facade_module.ChunkApi, "mark_indexed", AsyncMock())

    calls: list[str] = []
    monkeypatch.setattr(
        facade_module.QdrantIndexApi, "delete_by_document", _tracking(calls, "delete")
    )
    monkeypatch.setattr(facade_module.QdrantIndexApi, "upsert", _tracking(calls, "upsert"))

    points = [QdrantPoint(point_id=str(uuid.uuid4()), payload={})]
    facade = IngestionFacade(_postgres_yielding(MagicMock()), MagicMock(), MagicMock())
    await facade.index(collection_id, document_id, dense_dim=8, points=points)

    # The stale-point purge always precedes the upsert — a re-ingest REPLACES, never accumulates.
    assert calls == ["delete", "upsert"]


# --------------------------------------------------------------------------- #
# reingest — concurrent-run guard (Finding 1)
# --------------------------------------------------------------------------- #


async def test_reingest_admits_a_fresh_job_when_the_document_is_idle(monkeypatch) -> None:
    doc_id, coll_id, job_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    document = MagicMock(id=doc_id, collection_id=coll_id)
    job = MagicMock(id=job_id)
    monkeypatch.setattr(
        facade_module.DocumentApi, "get_for_update", AsyncMock(return_value=document)
    )
    monkeypatch.setattr(
        facade_module.JobApi, "get_active_for_document", AsyncMock(return_value=None)
    )
    create = AsyncMock(return_value=job)
    monkeypatch.setattr(facade_module.JobApi, "create", create)
    set_status = AsyncMock()
    monkeypatch.setattr(facade_module.DocumentApi, "set_status", set_status)

    facade = IngestionFacade(_postgres_yielding(MagicMock()), MagicMock(), MagicMock())
    result = await facade.reingest(doc_id)

    assert result.outcome is ReingestOutcome.ADMITTED
    assert result.document is document and result.job is job
    create.assert_awaited_once()
    set_status.assert_awaited_once()


async def test_reingest_refuses_a_document_that_already_has_an_active_job(monkeypatch) -> None:
    """The concurrency guard: a live (PENDING/RUNNING) job blocks a second concurrent run — otherwise
    two parallel runs interleave their Qdrant delete-by-document + upsert and strand orphan points."""
    doc_id, active_id = uuid.uuid4(), uuid.uuid4()
    document = MagicMock(id=doc_id, collection_id=uuid.uuid4())
    monkeypatch.setattr(
        facade_module.DocumentApi, "get_for_update", AsyncMock(return_value=document)
    )
    monkeypatch.setattr(
        facade_module.JobApi,
        "get_active_for_document",
        AsyncMock(return_value=MagicMock(id=active_id)),
    )
    create = AsyncMock()
    monkeypatch.setattr(facade_module.JobApi, "create", create)

    facade = IngestionFacade(_postgres_yielding(MagicMock()), MagicMock(), MagicMock())
    result = await facade.reingest(doc_id)

    assert result.outcome is ReingestOutcome.ALREADY_ACTIVE
    assert result.active_job_id == active_id
    create.assert_not_awaited()  # NO second concurrent job is minted


async def test_reingest_unknown_document_is_not_found_and_skips_the_active_probe(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        facade_module.DocumentApi, "get_for_update", AsyncMock(return_value=None)
    )
    get_active = AsyncMock()
    monkeypatch.setattr(facade_module.JobApi, "get_active_for_document", get_active)

    facade = IngestionFacade(_postgres_yielding(MagicMock()), MagicMock(), MagicMock())
    result = await facade.reingest(uuid.uuid4())

    assert result.outcome is ReingestOutcome.NOT_FOUND
    get_active.assert_not_awaited()  # an unknown id short-circuits before the active-job probe
