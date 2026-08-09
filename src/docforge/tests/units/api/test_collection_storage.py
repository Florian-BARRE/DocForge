"""Storage-footprint router: GET /collections/{id}/storage. The facade is mocked at the
CONTEXT.database.storage seam (no DB/Qdrant), so the test asserts the route wiring only — the 404
ladder on an unknown collection, and the 200 response SHAPE (s3/postgres/qdrant/grand_total_bytes and
the per-document breakdown) the frontend panel consumes. The aggregation math is locked separately in
test_storage_footprint_facade.py."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shared_libs.services.db import (
    CollectionFootprint,
    DocumentFootprint,
    PostgresFootprint,
    QdrantFootprint,
    S3Footprint,
)

COLLECTION_ID = "b7ac3cda-9070-4bd3-983c-27851179106b"
DOCUMENT_ID = "11111111-1111-1111-1111-111111111111"


def _fixed_footprint() -> CollectionFootprint:
    """A canned footprint with distinct per-store numbers so the shape assertions are unambiguous."""
    s3 = S3Footprint(
        original_bytes=1000, rendered_bytes=500, total_bytes=1500, physical_unique_bytes=1200
    )
    postgres = PostgresFootprint(
        documents_bytes=100,
        ir_blocks_bytes=200,
        enrichment_bytes=0,
        chunks_bytes=50,
        metadata_bytes=30,
        observability_bytes=40,
        total_bytes=420,
    )
    qdrant = QdrantFootprint(
        points=10, dense_bytes=40960, sparse_bytes=400, payload_bytes=2000, total_bytes=43360
    )
    document = DocumentFootprint(
        document_id=uuid.UUID(DOCUMENT_ID),
        filename="attention.pdf",
        s3=s3,
        postgres=postgres,
        qdrant=qdrant,
        total_bytes=45280,
    )
    return CollectionFootprint(
        collection_id=uuid.UUID(COLLECTION_ID),
        s3=s3,
        postgres=postgres,
        qdrant=qdrant,
        grand_total_bytes=45080,
        documents=[document],
    )


@pytest.fixture
def wired(fastapi_app, monkeypatch):
    """Patch the collection existence read + the storage facade; return the footprint mock."""
    from backend.context import CONTEXT  # noqa: PLC0415 — deferred until app/ is on sys.path

    monkeypatch.setattr(
        CONTEXT.database.collections, "get", AsyncMock(return_value=SimpleNamespace())
    )
    footprint = AsyncMock(return_value=_fixed_footprint())
    monkeypatch.setattr(CONTEXT.database.storage, "collection_footprint", footprint)
    return footprint


def test_storage_route_is_registered(fastapi_app) -> None:
    """The storage route must be part of the API contract (GET under the collection scope)."""
    paths = fastapi_app.openapi()["paths"]
    assert "get" in paths["/api/v1/collections/{collection_id}/storage"]


def test_storage_returns_full_shape(client, wired) -> None:
    """Happy path: 200 with the three per-store sections, grand total, and per-document breakdown."""
    response = client.get(f"/api/v1/collections/{COLLECTION_ID}/storage")
    assert response.status_code == 200, response.text
    body = response.json()

    # 1. Identity + the material grand total.
    assert body["collection_id"] == COLLECTION_ID
    assert body["grand_total_bytes"] == 45080

    # 2. S3 is EXACT — logical total vs deduped physical, flagged not-estimated.
    assert body["s3"]["total_bytes"] == 1500
    assert body["s3"]["physical_unique_bytes"] == 1200
    assert body["s3"]["estimated"] is False

    # 3. Postgres + Qdrant are ESTIMATES — the per-bucket detail is present and flagged.
    assert body["postgres"]["observability_bytes"] == 40
    assert body["postgres"]["total_bytes"] == 420
    assert body["postgres"]["estimated"] is True
    assert body["qdrant"]["dense_bytes"] == 40960
    assert body["qdrant"]["points"] == 10
    assert body["qdrant"]["estimated"] is True

    # 4. The per-document breakdown carries the same nested shape (doubles as the top-N).
    doc = body["documents"][0]
    assert doc["document_id"] == DOCUMENT_ID
    assert doc["filename"] == "attention.pdf"
    assert doc["total_bytes"] == 45280
    assert doc["s3"]["original_bytes"] == 1000
    assert doc["qdrant"]["total_bytes"] == 43360

    # 5. The facade was asked for exactly this collection.
    assert wired.await_args.args[0] == uuid.UUID(COLLECTION_ID)


def test_storage_unknown_collection_is_404(client, monkeypatch) -> None:
    """An unknown collection is a clean 404 — the footprint facade is never called."""
    from backend.context import CONTEXT  # noqa: PLC0415 — deferred until app/ is on sys.path

    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=None))
    footprint = AsyncMock()
    monkeypatch.setattr(CONTEXT.database.storage, "collection_footprint", footprint)

    response = client.get(f"/api/v1/collections/{COLLECTION_ID}/storage")

    assert response.status_code == 404, response.text
    footprint.assert_not_awaited()
