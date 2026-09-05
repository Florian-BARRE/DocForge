"""Cost-estimate router: POST /collections/{id}/estimate. The database façade is mocked at the
CONTEXT.database seam (no DB/S3), so the test asserts the route wiring and the 200 response SHAPE the
preview panel consumes: per-stage breakdown, projected volume, totals, surfaced assumptions and
caveats. The estimation math is locked separately in tests/units/estimate/. Also covers the 404 on an
unknown collection. The pipeline used is the stock default (local bge_server embed) so the estimate
is complete and free — the wiring, not a paid provider, is what this exercises."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shared_libs.pipelines.ingest.stages import IngestAssembler, default_state
from shared_libs.services.db.postgresql.tables import DocumentStatus

COLLECTION_ID = "b7ac3cda-9070-4bd3-983c-27851179106b"


def _default_pipeline_blob() -> dict:
    """The stock default pipeline blob (local embed on, enrich/metagen off)."""
    return IngestAssembler.assemble(default_state()).model_dump(mode="json")


def _pending_doc(file_size: int, page_count: int | None) -> SimpleNamespace:
    """A pending (uploaded, not-yet-ingested) PDF document row."""
    return SimpleNamespace(
        status=DocumentStatus.PENDING, format="pdf", file_size=file_size, page_count=page_count
    )


@pytest.fixture
def wired(fastapi_app, monkeypatch):
    """Patch the collection read, its schema, and its documents; return the collection mock."""
    from backend.context import CONTEXT  # noqa: PLC0415 — deferred until app/ is on sys.path

    collection = AsyncMock(return_value=SimpleNamespace(pipeline=_default_pipeline_blob()))
    monkeypatch.setattr(CONTEXT.database.collections, "get", collection)
    monkeypatch.setattr(CONTEXT.database.collections, "get_schema", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        CONTEXT.database.documents,
        "list_for_collection",
        AsyncMock(return_value=[_pending_doc(1_000_000, 20), _pending_doc(500_000, 10)]),
    )
    # The whole-collection scope now counts the covered set cheaply (bounded read + linear scaling).
    monkeypatch.setattr(
        CONTEXT.database.documents, "count_for_collection", AsyncMock(return_value=2)
    )
    return collection


def test_estimate_route_is_registered(fastapi_app) -> None:
    """The estimate route must be part of the API contract (POST under the collection scope)."""
    paths = fastapi_app.openapi()["paths"]
    assert "post" in paths["/api/v1/collections/{collection_id}/estimate"]


def test_estimate_returns_full_shape(client, wired) -> None:
    """Happy path: 200 with the per-stage breakdown, volume, totals, assumptions and caveats."""
    response = client.post(f"/api/v1/collections/{COLLECTION_ID}/estimate")
    assert response.status_code == 200
    body = response.json()

    # The stock pipeline covers both pending documents and embeds them locally (free, complete).
    assert body["document_count"] == 2
    assert body["cost_complete"] is True
    assert body["total_cost_usd"] == 0.0

    embed = next(s for s in body["stages"] if s["stage"] == "embed")
    assert embed["provider"] == "bge_server"
    assert embed["cost_usd"] == 0.0

    volume = body["volume"]
    assert volume["pages"] == 30  # 20 + 10, both probed exactly
    assert volume["chunks"] > 0
    assert volume["dense_vectors"] == volume["chunks"]

    assert body["assumptions"]["target_chunk_tokens"] > 0
    assert body["caveats"]  # at least the "these are estimates" caveat is always present


def test_estimate_body_scope_all_includes_every_document(client, wired) -> None:
    """scope=all bypasses the pending filter (here both docs are pending, so the count is stable)."""
    response = client.post(f"/api/v1/collections/{COLLECTION_ID}/estimate", json={"scope": "all"})
    assert response.status_code == 200
    assert response.json()["document_count"] == 2


def test_estimate_scope_is_bounded_and_scaled_to_true_count(
    client, fastapi_app, monkeypatch
) -> None:
    """The whole-collection scope measures only a bounded sample and scales to the TRUE count.

    ``count_for_collection`` reports 10 documents but only 2 rows are ever loaded (the sample); the
    estimate must reflect all 10 via linear scaling (document_count seam), never just the 2 measured.
    """
    from backend.context import CONTEXT  # noqa: PLC0415

    monkeypatch.setattr(
        CONTEXT.database.collections,
        "get",
        AsyncMock(return_value=SimpleNamespace(pipeline=_default_pipeline_blob())),
    )
    monkeypatch.setattr(CONTEXT.database.collections, "get_schema", AsyncMock(return_value=[]))
    # Only two rows are read (the bounded sample) even though the collection holds ten documents.
    list_for_collection = AsyncMock(
        return_value=[_pending_doc(1_000_000, 20), _pending_doc(500_000, 10)]
    )
    monkeypatch.setattr(CONTEXT.database.documents, "list_for_collection", list_for_collection)
    monkeypatch.setattr(
        CONTEXT.database.documents, "count_for_collection", AsyncMock(return_value=10)
    )

    response = client.post(f"/api/v1/collections/{COLLECTION_ID}/estimate")

    assert response.status_code == 200, response.text
    body = response.json()
    # The estimate covers all ten documents, scaled from the two measured — not just the sample.
    assert body["document_count"] == 10
    assert body["volume"]["pages"] == 150  # (20 + 10) pages * (10 / 2) scaling
    # A bounded read: the sample cap was passed through, never an unbounded whole-collection load.
    assert list_for_collection.await_args.kwargs["limit"] > 0


def test_estimate_unknown_collection_is_404(client, fastapi_app, monkeypatch) -> None:
    """An unknown collection is a 404, mirroring the other collection reads."""
    from backend.context import CONTEXT  # noqa: PLC0415

    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=None))
    response = client.post(f"/api/v1/collections/{uuid.uuid4()}/estimate")
    assert response.status_code == 404
