"""MetaVectorSyncFacade — denormalises a document's SEMANTIC/LEXICAL document-scope metadata onto
every one of its chunk Qdrant points as named vectors. Postgres + Qdrant + the embedder fully
mocked (pattern from test_filter_sync_facade.py): the test proves the values are embedded in ONE
batched pass per axis and written in ONE update_vectors call, and that the backfill PAGES through a
collection's documents instead of loading them all at once — never a real store or model."""

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from shared_libs.services.db.facades import MetaVectorSyncFacade
from shared_libs.services.db.facades import meta_vector_sync_facade as mvf_module
from shared_libs.services.db.qdrant import VectorNames


def _postgres_yielding(session: MagicMock) -> MagicMock:
    """A postgres mock whose session() is an async context manager yielding ``session``."""

    @asynccontextmanager
    async def _session():
        yield session

    postgres = MagicMock()
    postgres.session = _session
    return postgres


def _stub_common(monkeypatch, *, rows, chunk_ids, embedder) -> uuid.UUID:
    """Wire the shared read path (document, collection, rows, chunk ids, embedder, declared names)."""
    document_id = uuid.uuid4()
    collection_id = uuid.uuid4()
    document = MagicMock(id=document_id, collection_id=collection_id, pipeline={})
    collection = MagicMock(id=collection_id, pipeline={"nodes": []})
    monkeypatch.setattr(mvf_module.DocumentApi, "get", AsyncMock(return_value=document))
    monkeypatch.setattr(mvf_module.CollectionApi, "get", AsyncMock(return_value=collection))
    monkeypatch.setattr(
        mvf_module.DocumentApi, "get_searchable_metadata", AsyncMock(return_value=rows)
    )
    monkeypatch.setattr(
        mvf_module.ChunkApi, "get_indexed_ids_for_document", AsyncMock(return_value=chunk_ids)
    )
    monkeypatch.setattr(
        mvf_module.MetaVectorSyncHelpers, "find_embed_node", lambda pipeline: {"kind": "x"}
    )
    monkeypatch.setattr(
        mvf_module.MetaVectorSyncHelpers,
        "rebuild_embedder",
        lambda embed_node: (embedder, MagicMock()),
    )
    return document_id


async def test_sync_document_missing_returns_zero_and_no_qdrant_call(monkeypatch) -> None:
    monkeypatch.setattr(mvf_module.DocumentApi, "get", AsyncMock(return_value=None))
    update_vectors = AsyncMock()
    monkeypatch.setattr(mvf_module.QdrantIndexApi, "update_vectors", update_vectors)

    facade = MetaVectorSyncFacade(_postgres_yielding(MagicMock()), MagicMock())
    patched = await facade.sync_document_meta_vectors(uuid.uuid4())

    assert patched == 0
    update_vectors.assert_not_called()


async def test_sync_document_no_indexed_chunks_returns_zero(monkeypatch) -> None:
    embedder = MagicMock()
    embedder._embed_dense = AsyncMock()
    document_id = _stub_common(
        monkeypatch,
        rows=[("topic", "ai", True, False)],
        chunk_ids=[],
        embedder=embedder,
    )
    update_vectors = AsyncMock()
    monkeypatch.setattr(mvf_module.QdrantIndexApi, "update_vectors", update_vectors)

    facade = MetaVectorSyncFacade(_postgres_yielding(MagicMock()), MagicMock())
    patched = await facade.sync_document_meta_vectors(document_id)

    assert patched == 0
    update_vectors.assert_not_called()
    embedder._embed_dense.assert_not_called()


async def test_sync_document_embeds_dense_axis_in_one_batched_pass(monkeypatch) -> None:
    """Two semantic fields → ONE _embed_dense call over both values (not one call per field), and
    ONE update_vectors call carrying every chunk point."""
    chunk_ids = [uuid.uuid4(), uuid.uuid4()]
    rows = [("topic", "ai", True, False), ("author", "bob", True, False)]
    embedder = MagicMock()
    embedder._embed_dense = AsyncMock(return_value=[[0.1, 0.2], [0.3, 0.4]])
    embedder._embed_sparse = AsyncMock()
    document_id = _stub_common(monkeypatch, rows=rows, chunk_ids=chunk_ids, embedder=embedder)

    dense_names = {VectorNames.field_dense("topic"), VectorNames.field_dense("author")}
    monkeypatch.setattr(
        mvf_module.QdrantCollectionApi,
        "declared_vectors",
        AsyncMock(return_value=(dense_names, set())),
    )
    update_vectors = AsyncMock()
    monkeypatch.setattr(mvf_module.QdrantIndexApi, "update_vectors", update_vectors)
    qdrant = MagicMock()

    facade = MetaVectorSyncFacade(_postgres_yielding(MagicMock()), qdrant)
    patched = await facade.sync_document_meta_vectors(document_id)

    # 1. Every chunk point patched.
    assert patched == len(chunk_ids)
    # 2. ONE batched dense pass over BOTH values — never one forward pass per field.
    embedder._embed_dense.assert_awaited_once_with(["ai", "bob"])
    embedder._embed_sparse.assert_not_called()
    # 3. ONE update_vectors call carrying both points, each with both named dense vectors.
    update_vectors.assert_awaited_once()
    points = update_vectors.await_args.args[2]
    assert len(points) == len(chunk_ids)
    for point in points:
        assert set(point.dense) == dense_names


async def test_sync_document_embeds_sparse_axis_in_one_batched_pass(monkeypatch) -> None:
    """A lexical field is embedded through ONE _embed_sparse call and wrapped into the sparse map."""
    chunk_ids = [uuid.uuid4()]
    rows = [("topic", "ai", False, True), ("author", "bob", False, True)]
    embedder = MagicMock()
    embedder._embed_dense = AsyncMock()
    embedder._embed_sparse = AsyncMock(
        return_value=[
            SimpleNamespace(indices=[1, 2], values=[0.5, 0.6]),
            SimpleNamespace(indices=[3], values=[0.7]),
        ]
    )
    document_id = _stub_common(monkeypatch, rows=rows, chunk_ids=chunk_ids, embedder=embedder)

    sparse_names = {VectorNames.field_sparse("topic"), VectorNames.field_sparse("author")}
    monkeypatch.setattr(
        mvf_module.QdrantCollectionApi,
        "declared_vectors",
        AsyncMock(return_value=(set(), sparse_names)),
    )
    update_vectors = AsyncMock()
    monkeypatch.setattr(mvf_module.QdrantIndexApi, "update_vectors", update_vectors)

    facade = MetaVectorSyncFacade(_postgres_yielding(MagicMock()), MagicMock())
    patched = await facade.sync_document_meta_vectors(document_id)

    assert patched == 1
    embedder._embed_sparse.assert_awaited_once_with(["ai", "bob"])
    embedder._embed_dense.assert_not_called()
    point = update_vectors.await_args.args[2][0]
    assert set(point.sparse) == sparse_names


async def test_sync_document_dense_only_embedder_skips_lexical_axis(monkeypatch) -> None:
    """A dense-only embedder returns None for the sparse batch → lexical vectors skipped, no write."""
    chunk_ids = [uuid.uuid4()]
    rows = [("topic", "ai", False, True)]
    embedder = MagicMock()
    embedder._embed_sparse = AsyncMock(return_value=None)
    document_id = _stub_common(monkeypatch, rows=rows, chunk_ids=chunk_ids, embedder=embedder)

    monkeypatch.setattr(
        mvf_module.QdrantCollectionApi,
        "declared_vectors",
        AsyncMock(return_value=(set(), {VectorNames.field_sparse("topic")})),
    )
    update_vectors = AsyncMock()
    monkeypatch.setattr(mvf_module.QdrantIndexApi, "update_vectors", update_vectors)

    facade = MetaVectorSyncFacade(_postgres_yielding(MagicMock()), MagicMock())
    patched = await facade.sync_document_meta_vectors(document_id)

    # Nothing embeddable landed on any axis → clean no-op, no Qdrant write.
    assert patched == 0
    embedder._embed_sparse.assert_awaited_once()
    update_vectors.assert_not_called()


async def test_backfill_pages_through_documents(monkeypatch) -> None:
    """The backfill reads the collection in bounded pages (limit + advancing offset), stopping on a
    short page — it never loads the whole collection into memory."""
    collection_id = uuid.uuid4()
    doc1, doc2, doc3 = (MagicMock(id=uuid.uuid4()) for _ in range(3))
    list_for_collection = AsyncMock(side_effect=[[doc1, doc2], [doc3]])
    monkeypatch.setattr(mvf_module.DocumentApi, "list_for_collection", list_for_collection)

    facade = MetaVectorSyncFacade(_postgres_yielding(MagicMock()), MagicMock())
    facade._MetaVectorSyncFacade__BACKFILL_PAGE_SIZE = 2  # shrink the page for a two-page walk
    facade.sync_document_meta_vectors = AsyncMock(return_value=4)

    documents_synced, points_patched = await facade.backfill_collection_meta_vectors(collection_id)

    # 1. Every document across both pages was synced and aggregated.
    assert documents_synced == 3
    assert points_patched == 12
    # 2. Two bounded reads with an advancing offset — never a single unbounded list.
    assert list_for_collection.await_count == 2
    first, second = list_for_collection.await_args_list
    assert first.kwargs == {"limit": 2, "offset": 0}
    assert second.kwargs == {"limit": 2, "offset": 2}
