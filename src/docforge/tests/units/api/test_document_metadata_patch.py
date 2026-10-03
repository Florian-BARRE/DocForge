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


def _wire(monkeypatch, *, document, result=None, error=None, tracked_job_id=None):
    """Point CONTEXT.database + CONTEXT.queue at stubs; return the wired mocks.

    The router pre-creates a tracked ``metadata_sync`` job row (``jobs.create_metadata_sync``) and
    hands its id to the queue, which echoes it back as the returned job id — this mirrors that seam so
    the returned ``job_id`` is the DB row id, never arq's. Returns a namespace of the three handles.
    """
    from backend.context import CONTEXT  # noqa: PLC0415

    update = AsyncMock(side_effect=error) if error is not None else AsyncMock(return_value=result)
    documents = SimpleNamespace(get=AsyncMock(return_value=document))
    metadata_edit = SimpleNamespace(update_document_metadata=update)
    job_id = tracked_job_id if tracked_job_id is not None else uuid.uuid4()
    create_sync = AsyncMock(return_value=job_id)
    # The enqueue-failure cleanup: the router abandons a minted-but-unqueued row to free its lock.
    abandon = AsyncMock(return_value=None)
    jobs = SimpleNamespace(create_metadata_sync=create_sync, abandon=abandon)
    monkeypatch.setattr(
        CONTEXT,
        "database",
        SimpleNamespace(documents=documents, metadata_edit=metadata_edit, jobs=jobs),
    )
    # The real enqueue echoes back the DB job id it was handed — stub that so the response carries it.
    enqueue = AsyncMock(side_effect=lambda document_id, passed_job_id: passed_job_id)
    monkeypatch.setattr(CONTEXT, "queue", SimpleNamespace(enqueue_document_metadata_sync=enqueue))
    return SimpleNamespace(enqueue=enqueue, create_sync=create_sync, abandon=abandon, job_id=job_id)


# -------------------- happy paths --------------------
def test_semantic_change_enqueues_reembed(client, fastapi_app, edit_result, monkeypatch) -> None:
    """A changed semantic field pre-creates the tracked job row and returns ITS id (never arq's).

    The exact regression: the returned job_id must be the pre-created DB job row's id (kind=
    metadata_sync), so a poll of GET /jobs/{id} resolves instead of 404-ing on arq's internal id.
    """
    document = _document()
    result = edit_result(updated_fields=["abstract"], reembed_fields=["abstract"])
    wired = _wire(monkeypatch, document=document, result=result)

    response = client.patch(
        f"/api/v1/documents/{document.id}/metadata", json={"values": {"abstract": "x"}}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {
        "updated_fields": ["abstract"],
        "reembedding": True,
        "reembed_fields": ["abstract"],
        "job_id": str(wired.job_id),
    }
    # The tracked row is minted for this document + its collection, then its id is handed to the queue.
    wired.create_sync.assert_awaited_once_with(document.id, document.collection_id)
    wired.enqueue.assert_awaited_once_with(str(document.id), str(wired.job_id))


def test_filterable_only_change_does_not_enqueue(
    client, fastapi_app, edit_result, monkeypatch
) -> None:
    """A filterable-only change is fully handled synchronously — NO re-embed job, job_id null."""
    document = _document()
    result = edit_result(updated_fields=["topic"], reembed_fields=[])
    wired = _wire(monkeypatch, document=document, result=result)

    response = client.patch(
        f"/api/v1/documents/{document.id}/metadata", json={"values": {"topic": "ai"}}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reembedding"] is False
    assert body["job_id"] is None
    assert body["reembed_fields"] == []
    wired.create_sync.assert_not_awaited()
    wired.enqueue.assert_not_awaited()


def test_filter_repaint_failure_enqueues_repair(
    client, fastapi_app, edit_result, monkeypatch
) -> None:
    """A filterable-only edit whose inline repaint failed still schedules the repair job (so the stale
    Qdrant payload gets reconciled) and returns 200 — the committed write is never surfaced as a 500."""
    document = _document()
    result = edit_result(updated_fields=["topic"], reembed_fields=[], filter_repaint_failed=True)
    wired = _wire(monkeypatch, document=document, result=result)

    response = client.patch(
        f"/api/v1/documents/{document.id}/metadata", json={"values": {"topic": "ai"}}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reembedding"] is False
    assert body["job_id"] == str(wired.job_id)  # the durable repair job's tracked row id
    wired.create_sync.assert_awaited_once_with(document.id, document.collection_id)
    wired.enqueue.assert_awaited_once_with(str(document.id), str(wired.job_id))


def test_enqueue_failure_does_not_500(client, fastapi_app, edit_result, monkeypatch) -> None:
    """Redis unreachable when scheduling the re-embed must NOT surface the already-committed edit as a
    500 — the response is 200 with job_id null (the write landed; the re-embed just wasn't scheduled)."""
    document = _document()
    result = edit_result(updated_fields=["abstract"], reembed_fields=["abstract"])
    wired = _wire(monkeypatch, document=document, result=result)
    wired.enqueue.side_effect = RuntimeError("redis down")

    response = client.patch(
        f"/api/v1/documents/{document.id}/metadata", json={"values": {"abstract": "x"}}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["job_id"] is None
    assert body["reembedding"] is True
    # The row was minted before the enqueue blew up, so it is abandoned to free its active-job lock
    # (otherwise the PENDING row wedges the next edit/reingest and is never reaped).
    wired.abandon.assert_awaited_once()
    assert wired.abandon.await_args.args[0] == wired.job_id


def test_job_row_creation_failure_does_not_500(
    client, fastapi_app, edit_result, monkeypatch
) -> None:
    """A failure minting the tracked job row (e.g. the active-job unique guard) is best-effort too —
    the committed edit returns 200 with job_id null, and the queue is never contacted."""
    document = _document()
    result = edit_result(updated_fields=["abstract"], reembed_fields=["abstract"])
    wired = _wire(monkeypatch, document=document, result=result)
    wired.create_sync.side_effect = RuntimeError("active-job conflict")

    response = client.patch(
        f"/api/v1/documents/{document.id}/metadata", json={"values": {"abstract": "x"}}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["job_id"] is None
    assert body["reembedding"] is True
    wired.enqueue.assert_not_awaited()
    # No row was minted (create itself failed), so there is nothing to abandon.
    wired.abandon.assert_not_awaited()


def test_abandon_failure_after_enqueue_failure_does_not_500(
    client, fastapi_app, edit_result, monkeypatch
) -> None:
    """The cleanup is itself best-effort: enqueue fails AND abandon fails -> still 200, job_id null."""
    document = _document()
    result = edit_result(updated_fields=["abstract"], reembed_fields=["abstract"])
    wired = _wire(monkeypatch, document=document, result=result)
    wired.enqueue.side_effect = RuntimeError("redis down")
    wired.abandon.side_effect = RuntimeError("postgres down")

    response = client.patch(
        f"/api/v1/documents/{document.id}/metadata", json={"values": {"abstract": "x"}}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["job_id"] is None
    assert body["reembedding"] is True
    wired.abandon.assert_awaited_once()
    assert wired.abandon.await_args.args[0] == wired.job_id
    assert "enqueue failed" in wired.abandon.await_args.args[1]


def test_clear_only_edit_is_synchronous_no_job(
    client, fastapi_app, edit_result, monkeypatch
) -> None:
    """A clear (null) that removed its footprint inline reports the field, enqueues nothing, and
    forwards the null to the facade verbatim."""
    document = _document()
    result = edit_result(updated_fields=["topic"], reembed_fields=[])
    wired = _wire(monkeypatch, document=document, result=result)

    response = client.patch(
        f"/api/v1/documents/{document.id}/metadata", json={"values": {"topic": None}}
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "updated_fields": ["topic"],
        "reembedding": False,
        "reembed_fields": [],
        "job_id": None,
    }
    from backend.context import CONTEXT  # noqa: PLC0415

    CONTEXT.database.metadata_edit.update_document_metadata.assert_awaited_once_with(
        document.id, {"topic": None}
    )
    wired.create_sync.assert_not_awaited()
    wired.enqueue.assert_not_awaited()


def test_clear_qdrant_failure_enqueues_repair(
    client, fastapi_app, edit_result, monkeypatch
) -> None:
    """A clear whose inline Qdrant removal failed (flag set) still schedules the repair job."""
    document = _document()
    result = edit_result(updated_fields=["topic"], reembed_fields=[], filter_repaint_failed=True)
    wired = _wire(monkeypatch, document=document, result=result)

    response = client.patch(
        f"/api/v1/documents/{document.id}/metadata", json={"values": {"topic": None}}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reembedding"] is False
    assert body["job_id"] == str(wired.job_id)
    wired.enqueue.assert_awaited_once_with(str(document.id), str(wired.job_id))


def test_no_change_result_enqueues_nothing(client, fastapi_app, edit_result, monkeypatch) -> None:
    """A no-op edit (empty result) returns an empty, job-less response."""
    document = _document()
    wired = _wire(monkeypatch, document=document, result=edit_result())

    response = client.patch(
        f"/api/v1/documents/{document.id}/metadata", json={"values": {"topic": "ai"}}
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "updated_fields": [],
        "reembedding": False,
        "reembed_fields": [],
        "job_id": None,
    }
    wired.create_sync.assert_not_awaited()


def test_mixed_set_and_clear_reports_both_and_enqueues_once(
    client, fastapi_app, edit_result, monkeypatch
) -> None:
    document = _document()
    result = edit_result(updated_fields=["abstract", "topic"], reembed_fields=["abstract"])
    wired = _wire(monkeypatch, document=document, result=result)

    response = client.patch(
        f"/api/v1/documents/{document.id}/metadata",
        json={"values": {"abstract": "x", "topic": None}},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["updated_fields"] == ["abstract", "topic"]
    assert body["reembed_fields"] == ["abstract"]
    assert body["job_id"] == str(wired.job_id)
    wired.create_sync.assert_awaited_once()
    wired.enqueue.assert_awaited_once()


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
