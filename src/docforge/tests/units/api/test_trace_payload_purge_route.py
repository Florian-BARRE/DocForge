"""Trace-payload purge routes: reclaim the stored full execution-trace payloads of a whole collection
or a single document. The scope target must exist (404 for an unknown collection/document), the purge
itself is idempotent (a scope that stored nothing returns zeros, never a 404) and best-effort (the
façade never raises). No live stack — the façade is mocked.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

COLLECTION_ID = uuid.uuid4()
DOCUMENT_ID = uuid.uuid4()


def test_purge_routes_are_registered(fastapi_app) -> None:
    paths = fastapi_app.openapi()["paths"]
    assert "post" in paths["/api/v1/collections/{collection_id}/trace-payloads/purge"]
    assert "post" in paths["/api/v1/documents/{document_id}/trace-payloads/purge"]


def test_collection_purge_returns_counts(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    monkeypatch.setattr(
        CONTEXT.database.collections,
        "get",
        AsyncMock(return_value=SimpleNamespace(id=COLLECTION_ID)),
    )
    purge = AsyncMock(return_value=(12, 24))
    monkeypatch.setattr(CONTEXT.database.trace_payloads, "purge_for_collection", purge)

    response = client.post(f"/api/v1/collections/{COLLECTION_ID}/trace-payloads/purge")

    assert response.status_code == 200, response.text
    assert response.json() == {"purged_jobs": 12, "deleted_objects": 24}
    purge.assert_awaited_once_with(COLLECTION_ID)


def test_collection_purge_no_stored_trace_is_a_zero_no_op(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    monkeypatch.setattr(
        CONTEXT.database.collections,
        "get",
        AsyncMock(return_value=SimpleNamespace(id=COLLECTION_ID)),
    )
    monkeypatch.setattr(
        CONTEXT.database.trace_payloads, "purge_for_collection", AsyncMock(return_value=(0, 0))
    )

    response = client.post(f"/api/v1/collections/{COLLECTION_ID}/trace-payloads/purge")

    assert response.status_code == 200, response.text
    assert response.json() == {"purged_jobs": 0, "deleted_objects": 0}


def test_collection_purge_unknown_collection_is_404(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=None))
    purge = AsyncMock()
    monkeypatch.setattr(CONTEXT.database.trace_payloads, "purge_for_collection", purge)

    response = client.post(f"/api/v1/collections/{COLLECTION_ID}/trace-payloads/purge")

    assert response.status_code == 404, response.text
    purge.assert_not_awaited()


def test_document_purge_returns_counts(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    monkeypatch.setattr(
        CONTEXT.database.documents,
        "get",
        AsyncMock(return_value=SimpleNamespace(id=DOCUMENT_ID, collection_id=COLLECTION_ID)),
    )
    purge = AsyncMock(return_value=(3, 6))
    monkeypatch.setattr(CONTEXT.database.trace_payloads, "purge_for_document", purge)

    response = client.post(f"/api/v1/documents/{DOCUMENT_ID}/trace-payloads/purge")

    assert response.status_code == 200, response.text
    assert response.json() == {"purged_jobs": 3, "deleted_objects": 6}
    purge.assert_awaited_once_with(DOCUMENT_ID)


def test_document_purge_unknown_document_is_404(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    monkeypatch.setattr(CONTEXT.database.documents, "get", AsyncMock(return_value=None))
    purge = AsyncMock()
    monkeypatch.setattr(CONTEXT.database.trace_payloads, "purge_for_document", purge)

    response = client.post(f"/api/v1/documents/{DOCUMENT_ID}/trace-payloads/purge")

    assert response.status_code == 404, response.text
    purge.assert_not_awaited()
