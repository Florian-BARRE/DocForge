"""QdrantCollectionApi.ensure — the idempotent, concurrency-safe create path.

collection_exists()→create_collection is not atomic: several documents ingesting concurrently into
a BRAND-NEW collection can both see "missing" and both create it; the loser gets Qdrant's 409
"already exists". That is success (the winner built the same space), so ensure() must swallow the
409 and never fail the ingest — while any OTHER error still propagates. No real Qdrant here: the
client is mocked.
"""

import uuid
from unittest.mock import AsyncMock

import pytest
from qdrant_client.http.exceptions import UnexpectedResponse

from shared_libs.services.db.qdrant.apis.collection_api import QdrantCollectionApi


def _fresh_client() -> AsyncMock:
    """A client for which the collection does not yet exist (so ensure tries to create it)."""
    client = AsyncMock()
    client.collection_exists = AsyncMock(return_value=False)
    client.create_payload_index = AsyncMock()
    return client


async def test_ensure_swallows_the_409_already_exists_race() -> None:
    client = _fresh_client()
    client.create_collection = AsyncMock(
        side_effect=UnexpectedResponse(409, "Conflict", b'{"status":{"error":"already exists"}}', {})
    )
    # A concurrent creator won the race — ensure must return cleanly, not raise.
    await QdrantCollectionApi.ensure(client, f"col_{uuid.uuid4().hex}", dense_dim=8)
    client.create_collection.assert_awaited_once()


async def test_ensure_reraises_a_non_409_qdrant_error() -> None:
    client = _fresh_client()
    client.create_collection = AsyncMock(
        side_effect=UnexpectedResponse(500, "Internal", b'{"status":{"error":"boom"}}', {})
    )
    with pytest.raises(UnexpectedResponse):
        await QdrantCollectionApi.ensure(client, f"col_{uuid.uuid4().hex}", dense_dim=8)


async def test_ensure_short_circuits_when_the_collection_already_exists() -> None:
    client = _fresh_client()
    client.collection_exists = AsyncMock(return_value=True)
    client.create_collection = AsyncMock()
    await QdrantCollectionApi.ensure(client, f"col_{uuid.uuid4().hex}", dense_dim=8)
    client.create_collection.assert_not_awaited()  # never re-create an existing collection
