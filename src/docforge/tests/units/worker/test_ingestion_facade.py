"""IngestionFacade — the worker's persistence path (dedup, blob storage, the one-transaction
save, vector indexing). Never exercised before (mocked away entirely in test_jobs_core.py); this
proves its ACTUAL ordering + derivation contracts. Postgres/Qdrant/S3 fully mocked, same
``_postgres_yielding``-style session stub as test_filter_sync_facade.py — no real store touched.
"""

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from shared_libs.public_models import FieldType
from shared_libs.services.db.facades import (
    AdmissionResult,
    IngestionFacade,
    IngestionPayload,
    ReingestOutcome,
)
from shared_libs.services.db.facades import ingestion_facade as facade_module
from shared_libs.services.db.qdrant import PayloadType, QdrantPoint


def _integrity_error(constraint_name: str) -> IntegrityError:
    """An IntegrityError whose nested asyncpg cause carries ``constraint_name`` (the real shape)."""
    cause = SimpleNamespace(constraint_name=constraint_name)
    orig = SimpleNamespace(__cause__=cause)
    return IntegrityError("INSERT ...", {}, orig)


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

    # DONE with the denormalized chunk count (0 for an empty payload) and no warning by default.
    finalize_done.assert_awaited_once_with(ANY, document_id, warning_reason=None, chunk_count=0)


async def test_save_stamps_warning_and_chunk_count_on_finalize(monkeypatch) -> None:
    """A 0-chunk run reaches ``save`` with a warning_reason; a run with chunks stamps its count.
    Either way the count is denormalized (len of the payload's chunks) and the warning threads
    straight through to ``finalize_done``."""
    document_id = uuid.uuid4()
    _patch_save_apis(monkeypatch, [])
    finalize_done = AsyncMock()
    monkeypatch.setattr(facade_module.DocumentApi, "finalize_done", finalize_done)

    facade = IngestionFacade(
        _postgres_yielding(_session_with_flush()), MagicMock(), _s3_yielding(MagicMock())
    )
    await facade.save(document_id, IngestionPayload(), warning_reason="0 chunks — empty")

    finalize_done.assert_awaited_once_with(
        ANY, document_id, warning_reason="0 chunks — empty", chunk_count=0
    )


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
# store_trace_payloads
# --------------------------------------------------------------------------- #


def _flat(node_path: str, *, resolved_input=None, output=None):
    """A FlatNode stand-in carrying the two payload slots store_trace_payloads reads."""
    return SimpleNamespace(
        node_path=node_path,
        record=SimpleNamespace(resolved_input=resolved_input, output=output),
    )


async def test_store_trace_payloads_batches_into_one_put_many(monkeypatch) -> None:
    """Every node payload is accumulated and flushed in a SINGLE put_many (not one PUT per payload)."""
    nodes = [
        _flat("parse", resolved_input={"a": 1}, output={"b": 2}),
        _flat("chunk", resolved_input={"c": 3}, output={"d": 4}),
    ]
    monkeypatch.setattr(facade_module.ExecutionTreeFlattener, "flatten", lambda record: nodes)
    put_many = AsyncMock()
    monkeypatch.setattr(facade_module.S3ObjectApi, "put_many", put_many)
    set_bytes = AsyncMock()
    monkeypatch.setattr(facade_module.JobApi, "set_trace_payload_bytes", set_bytes)

    job_id = uuid.uuid4()
    facade = IngestionFacade(
        _postgres_yielding(MagicMock()), MagicMock(), _s3_yielding(MagicMock())
    )
    refs = await facade.store_trace_payloads(job_id, MagicMock(), max_payload_bytes=10_000)

    # One call, carrying all four payload objects (2 nodes × input+output).
    put_many.assert_awaited_once()
    objects = put_many.await_args.args[2]
    assert len(objects) == 4
    # Every node keeps both of its refs.
    assert set(refs) == {"parse", "chunk"}
    assert refs["parse"].input_ref and refs["parse"].output_ref
    # The summed footprint (deduped by content-addressed key) is recorded on the job row.
    expected = sum({obj.key: len(obj.data) for obj in objects}.values())
    set_bytes.assert_awaited_once_with(ANY, job_id, expected)
    assert set_bytes.await_args.args[2] > 0


async def test_store_trace_payloads_best_effort_drops_all_refs_on_failure(monkeypatch) -> None:
    """A batch store failure is swallowed (never raised) and drops every ref — trace never fails ingest."""
    nodes = [_flat("parse", resolved_input={"a": 1}, output={"b": 2})]
    monkeypatch.setattr(facade_module.ExecutionTreeFlattener, "flatten", lambda record: nodes)
    monkeypatch.setattr(
        facade_module.S3ObjectApi, "put_many", AsyncMock(side_effect=RuntimeError("s3 down"))
    )

    facade = IngestionFacade(MagicMock(), MagicMock(), _s3_yielding(MagicMock()))
    refs = await facade.store_trace_payloads(uuid.uuid4(), MagicMock(), max_payload_bytes=10_000)

    assert refs == {}


async def test_store_trace_payloads_noop_when_no_payloads(monkeypatch) -> None:
    """No full payloads attached → no put_many at all (the empty-pending short-circuit)."""
    nodes = [_flat("parse", resolved_input=None, output=None)]
    monkeypatch.setattr(facade_module.ExecutionTreeFlattener, "flatten", lambda record: nodes)
    put_many = AsyncMock()
    monkeypatch.setattr(facade_module.S3ObjectApi, "put_many", put_many)

    facade = IngestionFacade(MagicMock(), MagicMock(), _s3_yielding(MagicMock()))
    refs = await facade.store_trace_payloads(uuid.uuid4(), MagicMock(), max_payload_bytes=10_000)

    assert refs == {}
    put_many.assert_not_called()


async def test_store_trace_payloads_byte_accounting_failure_is_swallowed(monkeypatch) -> None:
    """A failure recording the byte total never fails an ingestion — the refs still come back."""
    nodes = [_flat("parse", resolved_input={"a": 1}, output={"b": 2})]
    monkeypatch.setattr(facade_module.ExecutionTreeFlattener, "flatten", lambda record: nodes)
    monkeypatch.setattr(facade_module.S3ObjectApi, "put_many", AsyncMock())
    monkeypatch.setattr(
        facade_module.JobApi,
        "set_trace_payload_bytes",
        AsyncMock(side_effect=RuntimeError("pg down")),
    )

    facade = IngestionFacade(
        _postgres_yielding(MagicMock()), MagicMock(), _s3_yielding(MagicMock())
    )
    refs = await facade.store_trace_payloads(uuid.uuid4(), MagicMock(), max_payload_bytes=10_000)

    # The store succeeded, so the node keeps its refs even though the byte-accounting write failed.
    assert set(refs) == {"parse"}


async def test_store_trace_payloads_counts_identical_overcap_payloads_once(monkeypatch) -> None:
    """Two BYTE-IDENTICAL over-cap payloads truncate to the same content key → counted ONCE. Guards
    the ``sum({key: len(data)})`` dedup against double-counting the shared object (and the marker)."""
    nodes = [
        _flat("parse", output={"x": "a" * 100}),
        _flat("chunk", output={"x": "a" * 100}),
    ]
    monkeypatch.setattr(facade_module.ExecutionTreeFlattener, "flatten", lambda record: nodes)
    put_many = AsyncMock()
    monkeypatch.setattr(facade_module.S3ObjectApi, "put_many", put_many)
    set_bytes = AsyncMock()
    monkeypatch.setattr(facade_module.JobApi, "set_trace_payload_bytes", set_bytes)

    facade = IngestionFacade(
        _postgres_yielding(MagicMock()), MagicMock(), _s3_yielding(MagicMock())
    )
    await facade.store_trace_payloads(uuid.uuid4(), MagicMock(), max_payload_bytes=20)

    # Both payloads over the cap collapse to ONE content-addressed (truncated) object.
    objects = put_many.await_args.args[2]
    assert len({obj.key for obj in objects}) == 1
    # The recorded total is that single object's size — not double the byte count.
    (only_object,) = {obj.key: obj for obj in objects}.values()
    set_bytes.assert_awaited_once_with(ANY, ANY, len(only_object.data))


async def test_store_trace_payloads_counts_distinct_overcap_payloads_twice(monkeypatch) -> None:
    """Two DISTINCT over-cap payloads have different content keys → both counted (sum of the two)."""
    nodes = [
        _flat("parse", output={"x": "a" * 100}),
        _flat("chunk", output={"x": "b" * 100}),
    ]
    monkeypatch.setattr(facade_module.ExecutionTreeFlattener, "flatten", lambda record: nodes)
    put_many = AsyncMock()
    monkeypatch.setattr(facade_module.S3ObjectApi, "put_many", put_many)
    set_bytes = AsyncMock()
    monkeypatch.setattr(facade_module.JobApi, "set_trace_payload_bytes", set_bytes)

    facade = IngestionFacade(
        _postgres_yielding(MagicMock()), MagicMock(), _s3_yielding(MagicMock())
    )
    await facade.store_trace_payloads(uuid.uuid4(), MagicMock(), max_payload_bytes=20)

    objects = put_many.await_args.args[2]
    by_key = {obj.key: obj for obj in objects}
    assert len(by_key) == 2  # distinct previews → distinct keys
    set_bytes.assert_awaited_once_with(ANY, ANY, sum(len(obj.data) for obj in by_key.values()))


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
    ensure = AsyncMock(return_value=set())
    delete_stale = AsyncMock()
    upsert = AsyncMock()
    mark_indexed = AsyncMock()
    monkeypatch.setattr(facade_module.QdrantCollectionApi, "ensure", ensure)
    monkeypatch.setattr(facade_module.QdrantIndexApi, "delete_stale_for_document", delete_stale)
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
    # 2. The points are upserted, then ONLY the document's leftover points (ids not produced by
    #    this run) are purged — scoped to this one document.
    upsert.assert_awaited_once_with(qdrant.raw, ANY, points)
    delete_stale.assert_awaited_once_with(
        qdrant.raw, ANY, document_id, [str(cid) for cid in chunk_ids]
    )
    # 3. Their chunks are flagged indexed by parsed point ids.
    mark_indexed.assert_awaited_once()
    marked_ids = mark_indexed.await_args.args[1]
    assert set(marked_ids) == set(chunk_ids)


async def test_index_upserts_before_purging_stale_points_so_a_failed_upsert_keeps_the_old_ones(
    monkeypatch,
) -> None:
    """Point ids are deterministic per (document, ordinal): the facade upserts FIRST (overwrite in
    place), THEN purges only the leftover ids. A failing upsert must leave the previous points
    untouched — never delete-then-upsert, which left the document with ZERO points on a failure."""
    collection_id = uuid.uuid4()
    document_id = uuid.uuid4()
    monkeypatch.setattr(facade_module.CollectionApi, "get_schema", AsyncMock(return_value=[]))
    monkeypatch.setattr(facade_module.QdrantCollectionApi, "ensure", AsyncMock(return_value=set()))
    monkeypatch.setattr(facade_module.ChunkApi, "mark_indexed", AsyncMock())
    full_delete = AsyncMock()
    monkeypatch.setattr(facade_module.QdrantIndexApi, "delete_by_document", full_delete)

    calls: list[str] = []
    monkeypatch.setattr(
        facade_module.QdrantIndexApi, "delete_stale_for_document", _tracking(calls, "purge")
    )
    monkeypatch.setattr(facade_module.QdrantIndexApi, "upsert", _tracking(calls, "upsert"))

    points = [QdrantPoint(point_id=str(uuid.uuid4()), payload={})]
    facade = IngestionFacade(_postgres_yielding(MagicMock()), MagicMock(), MagicMock())
    await facade.index(collection_id, document_id, dense_dim=8, points=points)
    assert calls == ["upsert", "purge"]
    full_delete.assert_not_awaited()

    # A failing upsert: nothing is deleted at all.
    purge = AsyncMock()
    monkeypatch.setattr(facade_module.QdrantIndexApi, "delete_stale_for_document", purge)
    monkeypatch.setattr(
        facade_module.QdrantIndexApi, "upsert", AsyncMock(side_effect=RuntimeError("qdrant down"))
    )
    with pytest.raises(RuntimeError):
        await facade.index(collection_id, document_id, dense_dim=8, points=points)
    purge.assert_not_awaited()
    full_delete.assert_not_awaited()


async def test_delete_stale_for_document_keeps_the_new_ids() -> None:
    """The purge filter is (document_id == X) AND NOT has_id(new ids) — the fresh points survive."""
    from shared_libs.services.db.qdrant.apis import index_api  # noqa: PLC0415

    client = MagicMock()
    client.delete = AsyncMock()
    document_id = uuid.uuid4()
    keep = [str(uuid.uuid4()), str(uuid.uuid4())]
    original = index_api.QdrantAliasApi.resolve_or_adopt
    index_api.QdrantAliasApi.resolve_or_adopt = AsyncMock(return_value=True)
    try:
        await index_api.QdrantIndexApi.delete_stale_for_document(client, "c", document_id, keep)
    finally:
        index_api.QdrantAliasApi.resolve_or_adopt = original
    selector = client.delete.await_args.kwargs["points_selector"]
    assert selector.must[0].match.value == str(document_id)
    assert list(selector.must_not[0].has_id) == keep


async def test_index_fails_clearly_on_an_undeclared_chunk_scope_vector(monkeypatch) -> None:
    """A chunk-scope semantic field whose named vector the store never declared would make Qdrant
    400 "Not existing vector name" on every ingest. The facade refuses BEFORE purging/upserting with
    a typed error (its class name is the job's error_type) naming the field and the rebuild route."""
    from shared_libs.services.db.facades.undeclared_vector_error import (  # noqa: PLC0415
        UndeclaredVectorError,
    )

    collection_id = uuid.uuid4()
    schema = [_field("Résumé", FieldType.TEXT, semantic=True)]
    monkeypatch.setattr(facade_module.CollectionApi, "get_schema", AsyncMock(return_value=schema))
    monkeypatch.setattr(facade_module.QdrantCollectionApi, "ensure", AsyncMock(return_value=set()))
    monkeypatch.setattr(
        facade_module.QdrantCollectionApi,
        "declared_vectors",
        AsyncMock(return_value=({"content_dense"}, {"content_bm25"})),
    )
    delete_by_document = AsyncMock()
    upsert = AsyncMock()
    monkeypatch.setattr(facade_module.QdrantIndexApi, "delete_by_document", delete_by_document)
    monkeypatch.setattr(facade_module.QdrantIndexApi, "upsert", upsert)

    points = [
        QdrantPoint(
            point_id=str(uuid.uuid4()),
            payload={},
            dense={"content_dense": [0.1], "meta_resume_dense": [0.2]},
        )
    ]
    facade = IngestionFacade(_postgres_yielding(MagicMock()), MagicMock(), MagicMock())
    with pytest.raises(UndeclaredVectorError) as exc:
        await facade.index(collection_id, uuid.uuid4(), dense_dim=1, points=points)

    assert type(exc.value).__name__ == "UndeclaredVectorError"
    assert str(exc.value) == (
        f"field 'Résumé' has no indexed vector in this collection — run rebuild_index "
        f"(POST /api/v1/collections/{collection_id}/rebuild-index)"
    )
    delete_by_document.assert_not_awaited()
    upsert.assert_not_awaited()


async def test_index_skips_the_store_read_for_content_only_points(monkeypatch) -> None:
    """No meta_* vector carried → no declared-vectors round-trip (zero cost on the common path)."""
    monkeypatch.setattr(facade_module.CollectionApi, "get_schema", AsyncMock(return_value=[]))
    monkeypatch.setattr(facade_module.QdrantCollectionApi, "ensure", AsyncMock(return_value=set()))
    declared = AsyncMock()
    monkeypatch.setattr(facade_module.QdrantCollectionApi, "declared_vectors", declared)
    monkeypatch.setattr(facade_module.QdrantIndexApi, "delete_stale_for_document", AsyncMock())
    monkeypatch.setattr(facade_module.QdrantIndexApi, "upsert", AsyncMock())
    monkeypatch.setattr(facade_module.ChunkApi, "mark_indexed", AsyncMock())

    points = [QdrantPoint(point_id=str(uuid.uuid4()), payload={}, dense={"content_dense": [0.1]})]
    facade = IngestionFacade(_postgres_yielding(MagicMock()), MagicMock(), MagicMock())
    await facade.index(uuid.uuid4(), uuid.uuid4(), dense_dim=1, points=points)

    declared.assert_not_awaited()


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
    # Reingest replaces the run, so it reclaims the document's PRIOR jobs' full-trace payloads
    # (best-effort, after the commit). Both the id-gather and the purge are mocked here.
    monkeypatch.setattr(
        facade_module.JobApi, "list_job_ids_for_document", AsyncMock(return_value=["old-job"])
    )
    trace_purge = AsyncMock(return_value=0)
    monkeypatch.setattr(facade_module.TracePurgeHelper, "purge", trace_purge)

    facade = IngestionFacade(_postgres_yielding(MagicMock()), MagicMock(), MagicMock())
    result = await facade.reingest(doc_id)

    assert result.outcome is ReingestOutcome.ADMITTED
    assert result.document is document and result.job is job
    create.assert_awaited_once()
    set_status.assert_awaited_once()
    # The prior run's trace payloads are purged with the captured job ids.
    trace_purge.assert_awaited_once()
    assert trace_purge.await_args.args[-1] == ["old-job"]


async def test_reingest_refuses_a_document_that_already_has_an_active_job(monkeypatch) -> None:
    """The concurrency guard: a live (PENDING/RUNNING) job blocks a second concurrent run — otherwise
    two parallel runs interleave their Qdrant upsert + stale-point purge and strand orphan points."""
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
    monkeypatch.setattr(facade_module.DocumentApi, "get_for_update", AsyncMock(return_value=None))
    get_active = AsyncMock()
    monkeypatch.setattr(facade_module.JobApi, "get_active_for_document", get_active)

    facade = IngestionFacade(_postgres_yielding(MagicMock()), MagicMock(), MagicMock())
    result = await facade.reingest(uuid.uuid4())

    assert result.outcome is ReingestOutcome.NOT_FOUND
    get_active.assert_not_awaited()  # an unknown id short-circuits before the active-job probe


# --------------------------------------------------------------------------- #
# admit — concurrent duplicate-upload race (check-then-insert → idempotent, not 500)
# --------------------------------------------------------------------------- #


async def test_admit_returns_created_when_the_insert_wins(monkeypatch) -> None:
    """The uncontended path: the document + job are inserted and returned as a fresh admission."""
    coll_id = uuid.uuid4()
    document = SimpleNamespace(
        id=uuid.uuid4(),
        collection_id=coll_id,
        source_hash="sha",
        pipeline_version="v1",
        filename="doc.pdf",
    )
    created = MagicMock(id=uuid.uuid4(), collection_id=coll_id)
    job = MagicMock(id=uuid.uuid4())
    monkeypatch.setattr(facade_module.DocumentApi, "create", AsyncMock(return_value=created))
    monkeypatch.setattr(facade_module.JobApi, "create", AsyncMock(return_value=job))
    find = AsyncMock()
    monkeypatch.setattr(facade_module.DocumentApi, "find", find)

    facade = IngestionFacade(_postgres_yielding(MagicMock()), MagicMock(), MagicMock())
    result = await facade.admit(document, MagicMock())

    assert isinstance(result, AdmissionResult)
    assert result.created is True
    assert result.document is created and result.job is job
    find.assert_not_awaited()  # no incumbent lookup on the happy path


async def test_admit_resolves_duplicate_race_to_the_incumbent_document(monkeypatch) -> None:
    """A concurrent upload of the same (collection, source_hash, version) won the insert; this loser
    hits the document UNIQUE constraint. It must resolve idempotently to the already-admitted
    document (created=False, no job) — the router turns that into the SAME duplicate response the
    dedup pre-check returns, never a 500."""
    coll_id = uuid.uuid4()
    document = SimpleNamespace(
        id=uuid.uuid4(),
        collection_id=coll_id,
        source_hash="sha",
        pipeline_version="v1",
        filename="doc.pdf",
    )
    incumbent = MagicMock(id=uuid.uuid4())
    session = MagicMock()
    session.rollback = AsyncMock()
    monkeypatch.setattr(
        facade_module.DocumentApi,
        "create",
        AsyncMock(side_effect=_integrity_error("uq_document_collection_id")),
    )
    find = AsyncMock(return_value=incumbent)
    monkeypatch.setattr(facade_module.DocumentApi, "find", find)
    job_create = AsyncMock()
    monkeypatch.setattr(facade_module.JobApi, "create", job_create)

    facade = IngestionFacade(_postgres_yielding(session), MagicMock(), MagicMock())
    result = await facade.admit(document, MagicMock())

    # The lost race is a clean idempotent duplicate — the incumbent, no job, and the aborted tx reset.
    assert result.created is False
    assert result.document is incumbent and result.job is None
    session.rollback.assert_awaited_once()
    find.assert_awaited_once_with(ANY, coll_id, "sha", "v1")
    job_create.assert_not_awaited()  # no job is minted for a duplicate


async def test_admit_reraises_an_unrelated_integrity_error(monkeypatch) -> None:
    """Only the document UNIQUE guard is swallowed — any OTHER integrity failure (e.g. a foreign-key
    violation) is a real, unexpected error and must still surface, never be masked as a duplicate."""
    coll_id = uuid.uuid4()
    document = SimpleNamespace(
        id=uuid.uuid4(),
        collection_id=coll_id,
        source_hash="sha",
        pipeline_version="v1",
        filename="doc.pdf",
    )
    session = MagicMock()
    session.rollback = AsyncMock()
    monkeypatch.setattr(
        facade_module.DocumentApi,
        "create",
        AsyncMock(side_effect=_integrity_error("fk_job_document_id_document")),
    )
    find = AsyncMock()
    monkeypatch.setattr(facade_module.DocumentApi, "find", find)

    facade = IngestionFacade(_postgres_yielding(session), MagicMock(), MagicMock())
    with pytest.raises(IntegrityError):
        await facade.admit(document, MagicMock())

    find.assert_not_awaited()  # an unrelated failure is not treated as a benign duplicate


async def _reingest_with_status(monkeypatch, status, replay_from):
    """Run an admitted reingest for a document in ``status``; return the set_status mock."""
    from shared_libs.services.db.facades import ingestion_facade as module  # noqa: PLC0415

    document = MagicMock(id=uuid.uuid4(), collection_id=uuid.uuid4(), status=status)
    monkeypatch.setattr(module.DocumentApi, "get_for_update", AsyncMock(return_value=document))
    monkeypatch.setattr(module.RebuildGuard, "assert_no_rebuild", AsyncMock())
    monkeypatch.setattr(module.JobApi, "get_active_for_document", AsyncMock(return_value=None))
    monkeypatch.setattr(module.IRApi, "has_blocks", AsyncMock(return_value=True))
    monkeypatch.setattr(module.JobApi, "list_job_ids_for_document", AsyncMock(return_value=[]))
    monkeypatch.setattr(module.JobApi, "create", AsyncMock(return_value=MagicMock()))
    monkeypatch.setattr(module.TracePurgeHelper, "purge", AsyncMock(return_value=0))
    set_status = AsyncMock()
    monkeypatch.setattr(module.DocumentApi, "set_status", set_status)
    facade = IngestionFacade(_postgres_yielding(MagicMock()), MagicMock(), MagicMock())
    result = await facade.reingest(document.id, replay_from=replay_from)
    assert result.outcome is ReingestOutcome.ADMITTED
    return set_status


async def test_replay_admission_keeps_a_done_or_failed_document_status(monkeypatch) -> None:
    """M-1: a replay does not reset a DONE/FAILED document to PENDING — so a failed replay can leave
    it exactly as it was (its old chunks/points are still served). A full run still resets it."""
    from shared_libs.services.db.postgresql.tables import DocumentStatus  # noqa: PLC0415

    for status in (DocumentStatus.DONE, DocumentStatus.FAILED):
        (await _reingest_with_status(monkeypatch, status, "chunk")).assert_not_awaited()
    (await _reingest_with_status(monkeypatch, DocumentStatus.DONE, None)).assert_awaited_once()
    (
        await _reingest_with_status(monkeypatch, DocumentStatus.CANCELLED, "chunk")
    ).assert_awaited_once()


async def test_flag_replay_failure_keeps_status_and_stamps_the_warning() -> None:
    from shared_libs.services.db.postgresql.apis import DocumentApi  # noqa: PLC0415
    from shared_libs.services.db.postgresql.tables import DocumentStatus  # noqa: PLC0415

    for prior, expected in (
        (DocumentStatus.DONE, DocumentStatus.DONE),
        (DocumentStatus.FAILED, DocumentStatus.FAILED),
        (DocumentStatus.PROCESSING, DocumentStatus.FAILED),
    ):
        document = SimpleNamespace(status=prior, warning_reason=None)
        session = MagicMock()
        session.get = AsyncMock(return_value=document)
        await DocumentApi.flag_replay_failure(session, uuid.uuid4(), "replay failed")
        assert document.status == expected and document.warning_reason == "replay failed"
