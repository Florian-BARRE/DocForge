"""QdrantCollectionApi.ensure / reconcile — the idempotent create-or-align path.

collection_exists()→create_collection is not atomic: several documents ingesting concurrently into
a BRAND-NEW collection can both see "missing" and both create it; the loser gets Qdrant's 409
"already exists". That is success (the winner built the same space), so ensure() must swallow the
409 and never fail the ingest — while any OTHER error still propagates.

When the collection ALREADY exists, ensure() no longer short-circuits: it RECONCILES the store with
the current schema — adding the payload indexes it is missing LIVE (a field toggled filterable after
first ingest becomes queryable without a reindex) and reporting the semantic/lexical fields whose
named vector Qdrant cannot add live (reindex-required). No real Qdrant here: the client is mocked.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from qdrant_client.http.exceptions import UnexpectedResponse

from shared_libs.services.db.qdrant import PayloadType, VectorNames
from shared_libs.services.db.qdrant.apis.collection_api import QdrantCollectionApi


def _fresh_client() -> AsyncMock:
    """A client for which the collection does not yet exist (so ensure tries to create it)."""
    client = AsyncMock()
    client.collection_exists = AsyncMock(return_value=False)
    client.create_payload_index = AsyncMock()
    return client


def _existing_client(*, payload_indexes: set[str], dense: set[str], sparse: set[str]) -> AsyncMock:
    """A client whose collection already exists, with the given payload indexes + named vectors."""
    client = AsyncMock()
    client.collection_exists = AsyncMock(return_value=True)
    client.create_collection = AsyncMock()
    client.create_payload_index = AsyncMock()
    info = SimpleNamespace(
        payload_schema={name: object() for name in payload_indexes},
        config=SimpleNamespace(
            params=SimpleNamespace(
                vectors={name: object() for name in dense},
                sparse_vectors={name: object() for name in sparse},
            )
        ),
    )
    client.get_collection = AsyncMock(return_value=info)
    return client


# ─────────────────────────── create path (fresh collection) ───────────────────────────


async def test_ensure_swallows_the_409_already_exists_race() -> None:
    client = _fresh_client()
    client.create_collection = AsyncMock(
        side_effect=UnexpectedResponse(
            409, "Conflict", b'{"status":{"error":"already exists"}}', {}
        )
    )
    # A concurrent creator won the race — ensure must return cleanly, not raise.
    assert await QdrantCollectionApi.ensure(client, f"col_{uuid.uuid4().hex}", dense_dim=8) == set()
    client.create_collection.assert_awaited_once()


async def test_ensure_reraises_a_non_409_qdrant_error() -> None:
    client = _fresh_client()
    client.create_collection = AsyncMock(
        side_effect=UnexpectedResponse(500, "Internal", b'{"status":{"error":"boom"}}', {})
    )
    with pytest.raises(UnexpectedResponse):
        await QdrantCollectionApi.ensure(client, f"col_{uuid.uuid4().hex}", dense_dim=8)


async def test_ensure_fresh_collection_reports_no_reindex() -> None:
    client = _fresh_client()
    client.create_collection = AsyncMock()
    result = await QdrantCollectionApi.ensure(
        client, f"col_{uuid.uuid4().hex}", dense_dim=8, semantic_fields=["author"]
    )
    # A fresh collection declares every named vector at creation — nothing is reindex-required.
    assert result == set()
    client.create_collection.assert_awaited_once()


# ─────────────────────────── reconcile path (existing collection) ───────────────────────────


async def test_ensure_existing_collection_never_recreates() -> None:
    client = _existing_client(
        payload_indexes={"document_id"}, dense={"content_dense"}, sparse=set()
    )
    await QdrantCollectionApi.ensure(client, f"col_{uuid.uuid4().hex}", dense_dim=8)
    client.create_collection.assert_not_awaited()  # never re-create an existing collection


async def test_reconcile_adds_only_the_missing_payload_index() -> None:
    # document_id is already indexed; a newly-filterable 'author' is not → only 'author' is added.
    client = _existing_client(payload_indexes={"document_id"}, dense=set(), sparse=set())
    result = await QdrantCollectionApi.ensure(
        client,
        f"col_{uuid.uuid4().hex}",
        dense_dim=8,
        filterable_fields={"author": PayloadType.KEYWORD},
    )
    client.create_payload_index.assert_awaited_once()
    assert client.create_payload_index.await_args.kwargs["field_name"] == "author"
    assert result == set()  # a filterable field needs no reindex — the index is added live


async def test_reconcile_is_idempotent_when_index_already_present() -> None:
    # Both document_id and the filterable field already carry an index → nothing is created.
    client = _existing_client(payload_indexes={"document_id", "author"}, dense=set(), sparse=set())
    await QdrantCollectionApi.ensure(
        client,
        f"col_{uuid.uuid4().hex}",
        dense_dim=8,
        filterable_fields={"author": PayloadType.KEYWORD},
    )
    client.create_payload_index.assert_not_awaited()


async def test_reconcile_flags_missing_named_vector_as_reindex_required() -> None:
    # 'summary' became semantic after ingest; its dense vector is NOT declared → reindex-required.
    declared = {VectorNames.CONTENT_DENSE}
    client = _existing_client(payload_indexes={"document_id"}, dense=declared, sparse=set())
    result = await QdrantCollectionApi.ensure(
        client, f"col_{uuid.uuid4().hex}", dense_dim=8, semantic_fields=["summary"]
    )
    assert result == {"summary"}


async def test_reconcile_declared_named_vector_needs_no_reindex() -> None:
    # 'summary' is semantic AND its dense vector is already declared → nothing to reindex.
    declared = {VectorNames.CONTENT_DENSE, VectorNames.field_dense("summary")}
    client = _existing_client(payload_indexes={"document_id"}, dense=declared, sparse=set())
    result = await QdrantCollectionApi.ensure(
        client, f"col_{uuid.uuid4().hex}", dense_dim=8, semantic_fields=["summary"]
    )
    assert result == set()
