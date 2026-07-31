"""Re-ingest route: re-run ingestion on an existing document's stored original — no delete + re-upload.

The facade returns (document, job) for a known id or None for an unknown one. The route creates a
fresh job, enqueues it (the worker refetches the original by source_hash and re-runs the collection's
current pipeline), and echoes the ids as 202; an unknown document is a 404 and nothing is enqueued.
No live stack — the ingestion facade and the queue are mocked.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

DOC_ID = uuid.uuid4()
JOB_ID = uuid.uuid4()


def test_reingest_route_is_registered(fastapi_app) -> None:
    paths = fastapi_app.openapi()["paths"]
    assert "post" in paths["/api/v1/documents/{document_id}/reingest"]


def test_reingest_creates_a_job_and_enqueues_it(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    document = SimpleNamespace(id=DOC_ID, collection_id=uuid.uuid4())
    job = SimpleNamespace(id=JOB_ID)
    reingest = AsyncMock(return_value=(document, job))
    enqueue = AsyncMock()
    monkeypatch.setattr(CONTEXT.database.ingestion, "reingest", reingest)
    monkeypatch.setattr(CONTEXT.queue, "enqueue_ingest", enqueue)

    response = client.post(f"/api/v1/documents/{DOC_ID}/reingest")

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["document_id"] == str(DOC_ID)
    assert body["job_id"] == str(JOB_ID)
    # The stored original is re-processed via the worker — ids only on the wire.
    enqueue.assert_awaited_once_with(str(DOC_ID), str(JOB_ID))
    assert reingest.await_args.args[0] == DOC_ID


def test_reingest_unknown_document_is_404_and_enqueues_nothing(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    reingest = AsyncMock(return_value=None)
    enqueue = AsyncMock()
    monkeypatch.setattr(CONTEXT.database.ingestion, "reingest", reingest)
    monkeypatch.setattr(CONTEXT.queue, "enqueue_ingest", enqueue)

    response = client.post(f"/api/v1/documents/{uuid.uuid4()}/reingest")

    assert response.status_code == 404, response.text
    enqueue.assert_not_awaited()
