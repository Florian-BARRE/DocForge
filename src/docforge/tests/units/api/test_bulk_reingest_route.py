"""Bulk re-ingest route: re-run the full pipeline over a collection's corpus (all or an explicit
subset). The collection must exist (404), the pipeline must be structurally sound (422 — validated
once, before any job is minted), and an explicit subset must exist AND belong to the collection
(422; empty list → 422). Each target gets a fresh job enqueued with the collection's budget. No
live stack — facades + queue mocked.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

COLLECTION_ID = uuid.uuid4()


def _patch_pipeline_validation(monkeypatch) -> None:
    """Make the fail-fast blob heal + structural validate no-ops (tested elsewhere)."""
    import importlib

    router_module = importlib.import_module("backend.routers.collections.router")

    monkeypatch.setattr(router_module.BlobNormalizer, "normalize", staticmethod(lambda blob: {}))
    monkeypatch.setattr(
        router_module.PipelineBlobValidator, "validate", classmethod(lambda cls, blob: None)
    )


def _collection() -> SimpleNamespace:
    return SimpleNamespace(id=COLLECTION_ID, job_timeout_seconds=None, pipeline={})


def test_bulk_reingest_route_is_registered(fastapi_app) -> None:
    paths = fastapi_app.openapi()["paths"]
    assert "post" in paths["/api/v1/collections/{collection_id}/reingest"]


def test_bulk_reingest_all_documents_fans_out(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    _patch_pipeline_validation(monkeypatch)
    docs = [SimpleNamespace(id=uuid.uuid4(), collection_id=COLLECTION_ID) for _ in range(3)]
    jobs = [SimpleNamespace(id=uuid.uuid4()) for _ in docs]
    enqueue = AsyncMock()
    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=_collection()))
    monkeypatch.setattr(CONTEXT.database.collections, "get_schema", AsyncMock(return_value=[]))
    # Whole-collection now routes through the shared DocumentSelector (filter mode, empty filter =
    # everything): the resolver projects ids, then the capped fan-out fetches the kept documents.
    monkeypatch.setattr(
        CONTEXT.database.documents,
        "resolve_query_ids",
        AsyncMock(return_value=[d.id for d in docs]),
    )
    monkeypatch.setattr(CONTEXT.database.documents, "get_by_ids", AsyncMock(return_value=docs))
    monkeypatch.setattr(
        CONTEXT.database.ingestion,
        "reingest",
        AsyncMock(side_effect=[(docs[i], jobs[i]) for i in range(3)]),
    )
    monkeypatch.setattr(CONTEXT.queue, "enqueue_ingest", enqueue)

    response = client.post(f"/api/v1/collections/{COLLECTION_ID}/reingest", json={})

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["count"] == 3
    assert body["matched"] == 3
    assert body["enqueued"] == 3
    assert body["capped"] is False
    assert len(body["jobs"]) == 3
    assert enqueue.await_count == 3


def test_bulk_reingest_explicit_subset_is_validated(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    _patch_pipeline_validation(monkeypatch)
    doc = SimpleNamespace(id=uuid.uuid4(), collection_id=COLLECTION_ID)
    job = SimpleNamespace(id=uuid.uuid4())
    enqueue = AsyncMock()
    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=_collection()))
    monkeypatch.setattr(CONTEXT.database.collections, "get_schema", AsyncMock(return_value=[]))
    # Id-mode selector: the resolver validates existence + ownership (get_by_ids), then the capped
    # fan-out fetches the kept documents (get_by_ids again) — the same mock serves both reads.
    monkeypatch.setattr(CONTEXT.database.documents, "get_by_ids", AsyncMock(return_value=[doc]))
    monkeypatch.setattr(CONTEXT.database.ingestion, "reingest", AsyncMock(return_value=(doc, job)))
    monkeypatch.setattr(CONTEXT.queue, "enqueue_ingest", enqueue)

    response = client.post(
        f"/api/v1/collections/{COLLECTION_ID}/reingest",
        json={"document_ids": [str(doc.id)]},
    )

    assert response.status_code == 202, response.text
    assert response.json()["count"] == 1
    enqueue.assert_awaited_once()


def test_bulk_reingest_rejects_empty_subset(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    _patch_pipeline_validation(monkeypatch)
    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=_collection()))

    response = client.post(
        f"/api/v1/collections/{COLLECTION_ID}/reingest", json={"document_ids": []}
    )

    assert response.status_code == 422
    assert "non-empty list" in response.json()["detail"]


def test_bulk_reingest_rejects_foreign_document(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    _patch_pipeline_validation(monkeypatch)
    foreign = SimpleNamespace(id=uuid.uuid4(), collection_id=uuid.uuid4())
    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=_collection()))
    monkeypatch.setattr(CONTEXT.database.collections, "get_schema", AsyncMock(return_value=[]))
    monkeypatch.setattr(CONTEXT.database.documents, "get_by_ids", AsyncMock(return_value=[foreign]))

    response = client.post(
        f"/api/v1/collections/{COLLECTION_ID}/reingest",
        json={"document_ids": [str(foreign.id)]},
    )

    assert response.status_code == 422
    assert "not in collection" in response.json()["detail"]


def test_bulk_reingest_unknown_collection_is_404(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=None))

    response = client.post(f"/api/v1/collections/{COLLECTION_ID}/reingest", json={})

    assert response.status_code == 404


def test_bulk_reingest_broken_pipeline_422s_before_any_spend(client, monkeypatch) -> None:
    """A stale/broken pipeline blob 422s BEFORE any job is minted or enqueued (fail-fast-before-spend)."""
    import importlib

    from backend.context import CONTEXT

    router_module = importlib.import_module("backend.routers.collections.router")

    def _raise(blob):
        raise router_module.BlobNormalizationError("broken node config")

    monkeypatch.setattr(router_module.BlobNormalizer, "normalize", staticmethod(_raise))
    reingest = AsyncMock()
    enqueue = AsyncMock()
    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=_collection()))
    monkeypatch.setattr(CONTEXT.database.ingestion, "reingest", reingest)
    monkeypatch.setattr(CONTEXT.queue, "enqueue_ingest", enqueue)

    response = client.post(f"/api/v1/collections/{COLLECTION_ID}/reingest", json={})

    assert response.status_code == 422
    reingest.assert_not_awaited()
    enqueue.assert_not_awaited()


def test_bulk_reingest_enqueue_failure_marks_job_failed_and_continues(client, monkeypatch) -> None:
    """A Redis blip on one doc marks THAT job failed (not an orphan PENDING) and doesn't sink the batch."""
    from backend.context import CONTEXT

    _patch_pipeline_validation(monkeypatch)
    docs = [SimpleNamespace(id=uuid.uuid4(), collection_id=COLLECTION_ID) for _ in range(2)]
    jobs = [SimpleNamespace(id=uuid.uuid4()) for _ in docs]
    mark_failed = AsyncMock()
    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=_collection()))
    monkeypatch.setattr(CONTEXT.database.collections, "get_schema", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        CONTEXT.database.documents,
        "resolve_query_ids",
        AsyncMock(return_value=[d.id for d in docs]),
    )
    monkeypatch.setattr(CONTEXT.database.documents, "get_by_ids", AsyncMock(return_value=docs))
    monkeypatch.setattr(
        CONTEXT.database.ingestion,
        "reingest",
        AsyncMock(side_effect=[(docs[0], jobs[0]), (docs[1], jobs[1])]),
    )
    monkeypatch.setattr(CONTEXT.database.jobs, "mark_failed", mark_failed)
    # First enqueue blows up (Redis blip), second succeeds — batch must survive.
    monkeypatch.setattr(
        CONTEXT.queue,
        "enqueue_ingest",
        AsyncMock(side_effect=[RuntimeError("redis down"), None]),
    )

    response = client.post(f"/api/v1/collections/{COLLECTION_ID}/reingest", json={})

    assert response.status_code == 202, response.text
    assert response.json()["count"] == 1  # only the second doc yielded a handle
    mark_failed.assert_awaited_once()
    assert mark_failed.await_args.args[0] == jobs[0].id
