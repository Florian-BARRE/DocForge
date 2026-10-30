"""Concurrent first ingests into a BRAND-NEW collection (issue #222).

While one job's ``create_collection`` is still running, Qdrant 1.20 already lists the collection
(``collection_exists`` is True) but a ``get_collection`` on it answers HTTP 500 "0 of 0 read
operations failed" (no shard ready yet). A job that reconciles the store, or reads its declared
vectors (the ingestion facade's ``_guard_declared_vectors``), at that moment must wait for the
collection to be ready instead of failing the ingest. A persistent 500 still propagates.
No real Qdrant here: a fake client mimics the creation window.
"""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from qdrant_client.http.exceptions import UnexpectedResponse

from shared_libs.public_models import VectorLayout
from shared_libs.services.db.qdrant import VectorNames
from shared_libs.services.db.qdrant.apis.collection_api import QdrantCollectionApi

NOT_READY = b'{"status":{"error":"Service internal error: 0 of 0 read operations failed"}}'


class CreatingQdrant:
    """A fake AsyncQdrantClient whose collection is listed before it can be read.

    ``create_collection`` registers the name at once, then stays "creating" for a few event-loop
    ticks; every ``get_collection`` in that window raises Qdrant 1.20's 500. A second creator gets
    the 409 ``ensure`` already tolerates.
    """

    def __init__(self, creation_ticks: int = 5) -> None:
        self.creation_ticks = creation_ticks
        self.listed: set[str] = set()
        self.ready: set[str] = set()
        self.dense: set[str] = set()
        self.sparse: set[str] = set()
        self.indexes: set[str] = set()
        self.not_ready_reads = 0

    async def collection_exists(self, name: str) -> bool:
        await asyncio.sleep(0)
        return name in self.listed

    async def create_collection(self, collection_name, vectors_config, sparse_vectors_config):
        if collection_name in self.listed:
            raise UnexpectedResponse(409, "Conflict", b'{"status":{"error":"already exists"}}', {})
        self.listed.add(collection_name)
        for _ in range(self.creation_ticks):
            await asyncio.sleep(0)
        self.dense = set((vectors_config or {}).keys())
        self.sparse = set((sparse_vectors_config or {}).keys())
        self.ready.add(collection_name)

    async def get_collection(self, name: str) -> SimpleNamespace:
        await asyncio.sleep(0)
        if name not in self.ready:
            self.not_ready_reads += 1
            raise UnexpectedResponse(500, "Internal Server Error", NOT_READY, {})
        return SimpleNamespace(
            payload_schema={index: object() for index in self.indexes},
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors={vector: object() for vector in self.dense},
                    sparse_vectors={
                        vector: SimpleNamespace(modifier=None) for vector in self.sparse
                    },
                )
            ),
        )

    async def create_payload_index(self, collection_name, field_name, field_schema) -> None:
        await asyncio.sleep(0)
        self.indexes.add(field_name)

    async def get_aliases(self) -> SimpleNamespace:
        return SimpleNamespace(aliases=[])

    async def get_collections(self) -> SimpleNamespace:
        return SimpleNamespace(collections=[])


@pytest.fixture(autouse=True)
def _instant_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the not-ready backoff on the event loop's tick (no wall-clock sleep in a unit test)."""
    monkeypatch.setattr(QdrantCollectionApi, "NOT_READY_BACKOFF_SECONDS", 0.0, raising=False)


async def _first_ingest(client: CreatingQdrant, name: str) -> set[str]:
    """What IngestionFacade.index does before the upsert: ensure, then read the declared vectors."""
    missing = await QdrantCollectionApi.ensure(
        client, name, dense_dim=8, layout=VectorLayout(dense=True, sparse=True)
    )
    declared = await QdrantCollectionApi.declared(client, name)
    assert VectorNames.CONTENT_DENSE in declared.dense
    return missing


async def test_concurrent_first_ingests_wait_for_the_collection_being_created() -> None:
    client = CreatingQdrant()
    name = f"col_{uuid.uuid4().hex}"
    # Six documents of a fresh collection index at once (the gate's 6-document ingest).
    results = await asyncio.gather(*(_first_ingest(client, name) for _ in range(6)))
    assert results == [set()] * 6
    assert client.not_ready_reads > 0  # the creation window was really hit


async def test_declared_waits_while_the_collection_is_being_created() -> None:
    client = CreatingQdrant()
    name = f"col_{uuid.uuid4().hex}"
    creating = asyncio.create_task(
        QdrantCollectionApi.ensure(client, name, dense_dim=8, layout=VectorLayout())
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    # Listed but not readable yet: the guard's read waits instead of failing the ingest.
    declared = await QdrantCollectionApi.declared(client, name)
    await creating
    assert VectorNames.CONTENT_DENSE in declared.dense
    assert client.not_ready_reads > 0


async def test_a_collection_that_never_becomes_ready_still_fails() -> None:
    client = CreatingQdrant()
    name = f"col_{uuid.uuid4().hex}"
    client.listed.add(name)  # listed forever, never ready: the retry is bounded
    with pytest.raises(UnexpectedResponse):
        await QdrantCollectionApi.declared(client, name)
    assert client.not_ready_reads == QdrantCollectionApi.NOT_READY_ATTEMPTS


async def test_another_500_is_not_retried() -> None:
    client = AsyncMock()
    client.collection_exists = AsyncMock(return_value=True)
    client.get_aliases = AsyncMock(return_value=SimpleNamespace(aliases=[]))
    client.get_collection = AsyncMock(
        side_effect=UnexpectedResponse(500, "Internal", b'{"status":{"error":"boom"}}', {})
    )
    with pytest.raises(UnexpectedResponse):
        await QdrantCollectionApi.declared(client, f"col_{uuid.uuid4().hex}")
    client.get_collection.assert_awaited_once()
