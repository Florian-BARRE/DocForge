"""FilterSyncFacade — denormalises a document's FILTERABLE document-scope metadata onto every one
of its chunk Qdrant points. Postgres + Qdrant fully mocked (pattern from test_search_exclusion.py):
the test proves WHAT gets read and WHAT gets written, never a real store."""

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

from shared_libs.services.db.facades import FilterSyncFacade
from shared_libs.services.db.facades import filter_sync_facade as fsf_module


def _postgres_yielding(session: MagicMock) -> MagicMock:
    """A postgres mock whose session() is an async context manager yielding ``session``."""

    @asynccontextmanager
    async def _session():
        yield session

    postgres = MagicMock()
    postgres.session = _session
    return postgres


async def test_sync_document_missing_returns_zero_and_no_qdrant_call(monkeypatch) -> None:
    monkeypatch.setattr(fsf_module.DocumentApi, "get", AsyncMock(return_value=None))
    set_payload = AsyncMock()
    monkeypatch.setattr(fsf_module.QdrantIndexApi, "set_payload", set_payload)

    facade = FilterSyncFacade(_postgres_yielding(MagicMock()), MagicMock())
    patched = await facade.sync_document_filter_payloads(uuid.uuid4())

    assert patched == 0
    set_payload.assert_not_called()


async def test_sync_document_no_filterable_values_returns_zero(monkeypatch) -> None:
    document_id = uuid.uuid4()
    collection_id = uuid.uuid4()
    document = MagicMock(id=document_id, collection_id=collection_id)
    monkeypatch.setattr(fsf_module.DocumentApi, "get", AsyncMock(return_value=document))
    monkeypatch.setattr(
        fsf_module.DocumentApi, "get_filterable_metadata", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        fsf_module.DocumentApi, "get_chunk_filterable_metadata", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        fsf_module.ChunkApi,
        "get_indexed_ids_for_document",
        AsyncMock(return_value=[uuid.uuid4()]),
    )
    set_payload = AsyncMock()
    monkeypatch.setattr(fsf_module.QdrantIndexApi, "set_payload", set_payload)

    facade = FilterSyncFacade(_postgres_yielding(MagicMock()), MagicMock())
    patched = await facade.sync_document_filter_payloads(document_id)

    assert patched == 0
    set_payload.assert_not_called()


async def test_sync_document_no_indexed_chunks_returns_zero(monkeypatch) -> None:
    document_id = uuid.uuid4()
    document = MagicMock(id=document_id, collection_id=uuid.uuid4())
    monkeypatch.setattr(fsf_module.DocumentApi, "get", AsyncMock(return_value=document))
    monkeypatch.setattr(
        fsf_module.DocumentApi, "get_filterable_metadata", AsyncMock(return_value={"topic": "ai"})
    )
    monkeypatch.setattr(
        fsf_module.DocumentApi, "get_chunk_filterable_metadata", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        fsf_module.ChunkApi, "get_indexed_ids_for_document", AsyncMock(return_value=[])
    )
    set_payload = AsyncMock()
    monkeypatch.setattr(fsf_module.QdrantIndexApi, "set_payload", set_payload)

    facade = FilterSyncFacade(_postgres_yielding(MagicMock()), MagicMock())
    patched = await facade.sync_document_filter_payloads(document_id)

    assert patched == 0
    set_payload.assert_not_called()


async def test_sync_document_happy_path_sets_payload_per_chunk(monkeypatch) -> None:
    document_id = uuid.uuid4()
    collection_id = uuid.uuid4()
    chunk_ids = [uuid.uuid4(), uuid.uuid4()]
    document = MagicMock(id=document_id, collection_id=collection_id)
    monkeypatch.setattr(fsf_module.DocumentApi, "get", AsyncMock(return_value=document))
    monkeypatch.setattr(
        fsf_module.DocumentApi,
        "get_filterable_metadata",
        AsyncMock(return_value={"topic": "ai", "year": 2026}),
    )
    monkeypatch.setattr(
        fsf_module.DocumentApi, "get_chunk_filterable_metadata", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        fsf_module.ChunkApi, "get_indexed_ids_for_document", AsyncMock(return_value=chunk_ids)
    )
    set_payload = AsyncMock()
    monkeypatch.setattr(fsf_module.QdrantIndexApi, "set_payload", set_payload)
    qdrant = MagicMock()

    facade = FilterSyncFacade(_postgres_yielding(MagicMock()), qdrant)
    patched = await facade.sync_document_filter_payloads(document_id)

    assert patched == len(chunk_ids)
    set_payload.assert_awaited_once()
    args = set_payload.await_args.args
    assert args[0] is qdrant.raw
    payloads = args[2]
    assert payloads == {str(cid): {"topic": "ai", "year": 2026} for cid in chunk_ids}


async def test_sync_document_merges_doc_and_chunk_scope_values(monkeypatch) -> None:
    """A CHUNK-scope filterable field (per-chunk value in chunk_metadata) is denormalised onto its
    OWN point, merged over the uniform document-scope keys — the repair path for a chunk-scope field
    toggled filterable after ingest. A chunk-scope key wins a name clash on its point."""
    document_id = uuid.uuid4()
    collection_id = uuid.uuid4()
    chunk_a, chunk_b = uuid.uuid4(), uuid.uuid4()
    document = MagicMock(id=document_id, collection_id=collection_id)
    monkeypatch.setattr(fsf_module.DocumentApi, "get", AsyncMock(return_value=document))
    monkeypatch.setattr(
        fsf_module.DocumentApi, "get_filterable_metadata", AsyncMock(return_value={"topic": "ai"})
    )
    # chunk_a carries its own section tag; chunk_b has no chunk-scope value (doc-scope keys only).
    monkeypatch.setattr(
        fsf_module.DocumentApi,
        "get_chunk_filterable_metadata",
        AsyncMock(return_value={chunk_a: {"section": "intro"}}),
    )
    monkeypatch.setattr(
        fsf_module.ChunkApi,
        "get_indexed_ids_for_document",
        AsyncMock(return_value=[chunk_a, chunk_b]),
    )
    set_payload = AsyncMock()
    monkeypatch.setattr(fsf_module.QdrantIndexApi, "set_payload", set_payload)
    qdrant = MagicMock()

    facade = FilterSyncFacade(_postgres_yielding(MagicMock()), qdrant)
    patched = await facade.sync_document_filter_payloads(document_id)

    assert patched == 2
    payloads = set_payload.await_args.args[2]
    assert payloads[str(chunk_a)] == {"topic": "ai", "section": "intro"}
    assert payloads[str(chunk_b)] == {"topic": "ai"}


async def test_backfill_aggregates_only_patched_documents(monkeypatch) -> None:
    collection_id = uuid.uuid4()
    doc_no_values = MagicMock(id=uuid.uuid4(), collection_id=collection_id)
    doc_patched = MagicMock(id=uuid.uuid4(), collection_id=collection_id)
    monkeypatch.setattr(
        fsf_module.DocumentApi,
        "list_for_collection",
        AsyncMock(return_value=[doc_no_values, doc_patched]),
    )

    async def _get(session, document_id):
        return doc_no_values if document_id == doc_no_values.id else doc_patched

    monkeypatch.setattr(fsf_module.DocumentApi, "get", _get)

    async def _filterable(session, document_id):
        return {} if document_id == doc_no_values.id else {"topic": "ai"}

    monkeypatch.setattr(fsf_module.DocumentApi, "get_filterable_metadata", _filterable)
    monkeypatch.setattr(
        fsf_module.DocumentApi, "get_chunk_filterable_metadata", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        fsf_module.ChunkApi,
        "get_indexed_ids_for_document",
        AsyncMock(return_value=[uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]),
    )
    monkeypatch.setattr(fsf_module.QdrantIndexApi, "set_payload", AsyncMock())

    facade = FilterSyncFacade(_postgres_yielding(MagicMock()), MagicMock())
    documents_synced, points_patched = await facade.backfill_collection_filter_payloads(
        collection_id
    )

    # 1. Only the document with a filterable value counted; its 3 indexed chunks patched.
    assert documents_synced == 1
    assert points_patched == 3
