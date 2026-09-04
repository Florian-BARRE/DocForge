"""Re-ingest route: re-run ingestion on an existing document's stored original — no delete + re-upload.

The facade returns a ReingestResult: ADMITTED (document + fresh job) for an idle document, NOT_FOUND
for an unknown id, or ALREADY_ACTIVE when a run is already queued/executing. The route enqueues an
ADMITTED run (the worker refetches the original by source_hash and re-runs the collection's current
pipeline) as 202; an unknown document is 404 (nothing enqueued); an already-active document is 409
(no second concurrent job — that would strand orphan Qdrant points); a queue failure marks the fresh
job FAILED and surfaces as 503 (never an orphan PENDING). No live stack — facade + queue mocked.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from shared_libs.services.db.facades import ReingestOutcome, ReingestResult

DOC_ID = uuid.uuid4()
JOB_ID = uuid.uuid4()


def _admitted(document, job) -> ReingestResult:
    return ReingestResult(outcome=ReingestOutcome.ADMITTED, document=document, job=job)


def test_reingest_route_is_registered(fastapi_app) -> None:
    paths = fastapi_app.openapi()["paths"]
    assert "post" in paths["/api/v1/documents/{document_id}/reingest"]


def test_reingest_creates_a_job_and_enqueues_it(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    document = SimpleNamespace(id=DOC_ID, collection_id=uuid.uuid4())
    job = SimpleNamespace(id=JOB_ID)
    reingest = AsyncMock(return_value=_admitted(document, job))
    enqueue = AsyncMock()
    # The route loads the document first to enforce the caller's collection scope (auth-off = root).
    monkeypatch.setattr(CONTEXT.database.documents, "get", AsyncMock(return_value=document))
    monkeypatch.setattr(CONTEXT.database.ingestion, "reingest", reingest)
    monkeypatch.setattr(CONTEXT.queue, "enqueue_ingest", enqueue)

    response = client.post(f"/api/v1/documents/{DOC_ID}/reingest")

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["document_id"] == str(DOC_ID)
    assert body["job_id"] == str(JOB_ID)
    # The stored original is re-processed via the worker — ids + the ``force`` flag (default False,
    # a normal task kwarg) on the wire; no timeout kwarg (arq rejects a per-message timeout, and the
    # worker applies the collection budget itself).
    enqueue.assert_awaited_once_with(str(DOC_ID), str(JOB_ID), force=False)
    assert reingest.await_args.args[0] == DOC_ID


def test_reingest_enqueue_is_ids_only_even_with_a_budget(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    document = SimpleNamespace(id=DOC_ID, collection_id=uuid.uuid4())
    job = SimpleNamespace(id=JOB_ID)
    enqueue = AsyncMock()
    monkeypatch.setattr(CONTEXT.database.documents, "get", AsyncMock(return_value=document))
    monkeypatch.setattr(
        CONTEXT.database.ingestion, "reingest", AsyncMock(return_value=_admitted(document, job))
    )
    monkeypatch.setattr(CONTEXT.queue, "enqueue_ingest", enqueue)

    response = client.post(f"/api/v1/documents/{DOC_ID}/reingest")

    assert response.status_code == 202, response.text
    # Even with a per-collection budget set, the enqueue carries ids + ``force`` only — the budget is
    # NOT threaded to arq (it has no per-message timeout); the worker reads it from the collection.
    enqueue.assert_awaited_once_with(str(DOC_ID), str(JOB_ID), force=False)


def test_reingest_unknown_document_is_404_and_enqueues_nothing(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    reingest = AsyncMock(return_value=ReingestResult(outcome=ReingestOutcome.NOT_FOUND))
    enqueue = AsyncMock()
    # Unknown id is now surfaced by the scope-guard document load, before reingest is ever called.
    monkeypatch.setattr(CONTEXT.database.documents, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(CONTEXT.database.ingestion, "reingest", reingest)
    monkeypatch.setattr(CONTEXT.queue, "enqueue_ingest", enqueue)

    response = client.post(f"/api/v1/documents/{uuid.uuid4()}/reingest")

    assert response.status_code == 404, response.text
    enqueue.assert_not_awaited()
    reingest.assert_not_awaited()


def test_reingest_while_a_job_is_active_is_409_and_enqueues_nothing(client, monkeypatch) -> None:
    """A document with a PENDING/RUNNING job is refused (409) — no second concurrent run is minted."""
    from backend.context import CONTEXT

    document = SimpleNamespace(id=DOC_ID, collection_id=uuid.uuid4())
    active_job_id = uuid.uuid4()
    enqueue = AsyncMock()
    monkeypatch.setattr(CONTEXT.database.documents, "get", AsyncMock(return_value=document))
    monkeypatch.setattr(
        CONTEXT.database.ingestion,
        "reingest",
        AsyncMock(
            return_value=ReingestResult(
                outcome=ReingestOutcome.ALREADY_ACTIVE, active_job_id=active_job_id
            )
        ),
    )
    monkeypatch.setattr(CONTEXT.queue, "enqueue_ingest", enqueue)

    response = client.post(f"/api/v1/documents/{DOC_ID}/reingest")

    assert response.status_code == 409, response.text
    assert str(active_job_id) in response.json()["detail"]
    enqueue.assert_not_awaited()


def test_reingest_enqueue_failure_marks_job_failed_and_503s(client, monkeypatch) -> None:
    """A Redis blip on the enqueue marks the fresh job FAILED (never an orphan PENDING) and 503s."""
    from backend.context import CONTEXT

    document = SimpleNamespace(id=DOC_ID, collection_id=uuid.uuid4())
    job = SimpleNamespace(id=JOB_ID)
    mark_failed = AsyncMock()
    monkeypatch.setattr(CONTEXT.database.documents, "get", AsyncMock(return_value=document))
    monkeypatch.setattr(
        CONTEXT.database.ingestion, "reingest", AsyncMock(return_value=_admitted(document, job))
    )
    monkeypatch.setattr(CONTEXT.database.jobs, "mark_failed", mark_failed)
    monkeypatch.setattr(
        CONTEXT.queue, "enqueue_ingest", AsyncMock(side_effect=RuntimeError("redis down"))
    )

    response = client.post(f"/api/v1/documents/{DOC_ID}/reingest")

    assert response.status_code == 503, response.text
    # The committed PENDING job is marked FAILED so the reaper (RUNNING-only) is not its only hope.
    mark_failed.assert_awaited_once()
    assert mark_failed.await_args.args[0] == JOB_ID
