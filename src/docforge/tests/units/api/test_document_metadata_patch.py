"""PATCH /documents/{id}/metadata — the metadata value-edit endpoint.

Serviceless: CONTEXT.database (documents + metadata_edit) and CONTEXT.queue are stubbed (pattern
from test_document_views.py). The tests prove the request/response contract and the ONE behavioural
decision the router owns: the re-embed job is enqueued IFF a changed field is semantic/lexical.

`from backend...` / `from shared_libs...` imports are deferred behind the fastapi_app fixture so
module import never runs before the app puts app/ on sys.path and the shared_libs alias is live.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


# -------------------- fixtures --------------------
@pytest.fixture
def edit_result(fastapi_app):
    """The facade result dataclass, imported after the shared_libs alias is live."""
    from shared_libs.services.db.facades import MetadataEditResult  # noqa: PLC0415

    return MetadataEditResult


def _document() -> SimpleNamespace:
    """A minimal document row carrying only the collection id the scope guard reads."""
    return SimpleNamespace(id=uuid.uuid4(), collection_id=uuid.uuid4())


def _wire(monkeypatch, *, document, result=None, error=None) -> AsyncMock:
    """Point CONTEXT.database + CONTEXT.queue at stubs; return the queue enqueue mock."""
    from backend.context import CONTEXT  # noqa: PLC0415

    update = AsyncMock(side_effect=error) if error is not None else AsyncMock(return_value=result)
    documents = SimpleNamespace(get=AsyncMock(return_value=document))
    metadata_edit = SimpleNamespace(update_document_metadata=update)
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(documents=documents, metadata_edit=metadata_edit)
    )
    enqueue = AsyncMock(return_value="job-123")
    monkeypatch.setattr(CONTEXT, "queue", SimpleNamespace(enqueue_document_metadata_sync=enqueue))
    return enqueue


# -------------------- happy paths --------------------
def test_semantic_change_enqueues_reembed(client, fastapi_app, edit_result, monkeypatch) -> None:
    """A changed semantic field enqueues the re-embed job and returns its id + reembedding=True."""
    document = _document()
    result = edit_result(updated_fields=["abstract"], reembed_fields=["abstract"])
    enqueue = _wire(monkeypatch, document=document, result=result)

    response = client.patch(
        f"/api/v1/documents/{document.id}/metadata", json={"values": {"abstract": "x"}}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {
        "updated_fields": ["abstract"],
        "reembedding": True,
        "reembed_fields": ["abstract"],
        "job_id": "job-123",
    }
    enqueue.assert_awaited_once_with(str(document.id))


def test_filterable_only_change_does_not_enqueue(
    client, fastapi_app, edit_result, monkeypatch
) -> None:
    """A filterable-only change is fully handled synchronously — NO re-embed job, job_id null."""
    document = _document()
    result = edit_result(updated_fields=["topic"], reembed_fields=[])
    enqueue = _wire(monkeypatch, document=document, result=result)

    response = client.patch(
        f"/api/v1/documents/{document.id}/metadata", json={"values": {"topic": "ai"}}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reembedding"] is False
    assert body["job_id"] is None
    assert body["reembed_fields"] == []
    enqueue.assert_not_awaited()


def test_filter_repaint_failure_enqueues_repair(
    client, fastapi_app, edit_result, monkeypatch
) -> None:
    """A filterable-only edit whose inline repaint failed still schedules the repair job (so the stale
    Qdrant payload gets reconciled) and returns 200 — the committed write is never surfaced as a 500."""
    document = _document()
    result = edit_result(updated_fields=["topic"], reembed_fields=[], filter_repaint_failed=True)
    enqueue = _wire(monkeypatch, document=document, result=result)

    response = client.patch(
        f"/api/v1/documents/{document.id}/metadata", json={"values": {"topic": "ai"}}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reembedding"] is False
    assert body["job_id"] == "job-123"  # the durable repair job
    enqueue.assert_awaited_once_with(str(document.id))


def test_enqueue_failure_does_not_500(client, fastapi_app, edit_result, monkeypatch) -> None:
    """Redis unreachable when scheduling the re-embed must NOT surface the already-committed edit as a
    500 — the response is 200 with job_id null (the write landed; the re-embed just wasn't scheduled)."""
    document = _document()
    result = edit_result(updated_fields=["abstract"], reembed_fields=["abstract"])
    enqueue = _wire(monkeypatch, document=document, result=result)
    enqueue.side_effect = RuntimeError("redis down")

    response = client.patch(
        f"/api/v1/documents/{document.id}/metadata", json={"values": {"abstract": "x"}}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["job_id"] is None
    assert body["reembedding"] is True


# -------------------- error mapping --------------------
def test_unknown_document_is_404(client, fastapi_app, monkeypatch) -> None:
    """An unknown document id is a 404 before the facade is called."""
    _wire(monkeypatch, document=None, result=None)

    response = client.patch(
        f"/api/v1/documents/{uuid.uuid4()}/metadata", json={"values": {"topic": "ai"}}
    )

    assert response.status_code == 404


def test_validation_error_is_422(client, fastapi_app, monkeypatch) -> None:
    """A facade MetadataValidationError surfaces as a 422 carrying the per-field messages."""
    from shared_libs.services.db.facades import MetadataValidationError  # noqa: PLC0415

    document = _document()
    _wire(
        monkeypatch,
        document=document,
        error=MetadataValidationError(["unknown field 'nope'"]),
    )

    response = client.patch(
        f"/api/v1/documents/{document.id}/metadata", json={"values": {"nope": "x"}}
    )

    assert response.status_code == 422
    assert "unknown field 'nope'" in response.json()["detail"]


def test_not_found_from_facade_is_404(client, fastapi_app, monkeypatch) -> None:
    """A document that vanished in the race window (facade not-found) maps to 404, not 500."""
    from shared_libs.services.db.facades import MetadataEditNotFoundError  # noqa: PLC0415

    document = _document()
    _wire(monkeypatch, document=document, error=MetadataEditNotFoundError(document.id))

    response = client.patch(
        f"/api/v1/documents/{document.id}/metadata", json={"values": {"topic": "ai"}}
    )

    assert response.status_code == 404


def test_empty_values_is_422(client, fastapi_app, monkeypatch) -> None:
    """An empty values map is rejected by the request model (min_length=1)."""
    document = _document()
    _wire(monkeypatch, document=document, result=None)

    response = client.patch(f"/api/v1/documents/{document.id}/metadata", json={"values": {}})

    assert response.status_code == 422


def test_route_is_registered(fastapi_app) -> None:
    """The endpoint appears in the OpenAPI contract as a PATCH sibling of /enabled."""
    paths = fastapi_app.openapi()["paths"]
    assert "patch" in paths["/api/v1/documents/{document_id}/metadata"]
