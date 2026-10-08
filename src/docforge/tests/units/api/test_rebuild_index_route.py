"""rebuild_index API surface: the admission route (202 / 404 / 409 active / 409 busy / 503), the
409 ``rebuild_index_active`` on upload + single + bulk reingest while a rebuild is live, and the bulk
reingest 409 ``rebuild_index_required`` while the store lacks a named vector. Facades + queue mocked.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from shared_libs.services.db.facades import CollectionBusyError, IndexRebuildActiveError

COLLECTION_ID = uuid.uuid4()
JOB_ID = uuid.uuid4()
ROUTE = f"/api/v1/collections/{COLLECTION_ID}/rebuild-index"


def test_rebuild_route_is_registered(fastapi_app) -> None:
    paths = fastapi_app.openapi()["paths"]
    assert "post" in paths["/api/v1/collections/{collection_id}/rebuild-index"]


def test_rebuild_admits_and_enqueues(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    enqueue = AsyncMock(return_value=str(JOB_ID))
    monkeypatch.setattr(CONTEXT.database.index_rebuild, "admit", AsyncMock(return_value=JOB_ID))
    monkeypatch.setattr(CONTEXT.queue, "enqueue_rebuild_index", enqueue)

    response = client.post(ROUTE)

    assert response.status_code == 202, response.text
    assert response.json() == {"collection_id": str(COLLECTION_ID), "job_id": str(JOB_ID)}
    enqueue.assert_awaited_once_with(str(COLLECTION_ID), str(JOB_ID))


def test_rebuild_unknown_collection_is_404(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    monkeypatch.setattr(
        CONTEXT.database.index_rebuild, "admit", AsyncMock(side_effect=LookupError("nope"))
    )
    assert client.post(ROUTE).status_code == 404


def test_rebuild_already_active_is_409(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    error = IndexRebuildActiveError(COLLECTION_ID, JOB_ID)
    monkeypatch.setattr(CONTEXT.database.index_rebuild, "admit", AsyncMock(side_effect=error))

    response = client.post(ROUTE)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "rebuild_index_active"
    assert response.json()["detail"]["job_id"] == str(JOB_ID)


def test_rebuild_on_busy_collection_is_409(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    error = CollectionBusyError(COLLECTION_ID, [JOB_ID])
    monkeypatch.setattr(CONTEXT.database.index_rebuild, "admit", AsyncMock(side_effect=error))

    response = client.post(ROUTE)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "collection_busy"
    assert response.json()["detail"]["job_ids"] == [str(JOB_ID)]


def test_rebuild_enqueue_failure_abandons_the_job(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    abandon = AsyncMock()
    monkeypatch.setattr(CONTEXT.database.index_rebuild, "admit", AsyncMock(return_value=JOB_ID))
    monkeypatch.setattr(
        CONTEXT.queue, "enqueue_rebuild_index", AsyncMock(side_effect=ConnectionError("redis"))
    )
    monkeypatch.setattr(CONTEXT.database.jobs, "abandon", abandon)

    assert client.post(ROUTE).status_code == 503
    assert abandon.await_args.args[0] == JOB_ID


def test_single_reingest_during_rebuild_is_409(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    document = SimpleNamespace(id=uuid.uuid4(), collection_id=COLLECTION_ID)
    monkeypatch.setattr(CONTEXT.database.documents, "get", AsyncMock(return_value=document))
    monkeypatch.setattr(
        CONTEXT.database.ingestion,
        "reingest",
        AsyncMock(side_effect=IndexRebuildActiveError(COLLECTION_ID, JOB_ID)),
    )

    response = client.post(f"/api/v1/documents/{document.id}/reingest")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "rebuild_index_active"


def test_upload_during_rebuild_is_409(client, monkeypatch, real_rebuild_guards) -> None:
    from backend.context import CONTEXT

    collection = SimpleNamespace(
        id=COLLECTION_ID, pipeline={}, supported_formats=None, max_file_size_mb=None
    )
    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=collection))
    monkeypatch.setattr(
        CONTEXT.database.index_rebuild,
        "active_rebuild",
        AsyncMock(return_value=SimpleNamespace(id=JOB_ID)),
    )
    import importlib

    router_module = importlib.import_module("backend.routers.documents.router")
    monkeypatch.setattr(router_module.BlobNormalizer, "normalize", staticmethod(lambda blob: {}))
    monkeypatch.setattr(
        router_module.PipelineBlobValidator, "validate", classmethod(lambda cls, blob: None)
    )

    response = client.post(
        "/api/v1/documents",
        files={"file": ("a.md", b"# hello\n", "text/markdown")},
        data={"collection_id": str(COLLECTION_ID)},
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "rebuild_index_active"


def _patch_bulk(monkeypatch) -> None:
    import importlib

    from backend.context import CONTEXT

    router_module = importlib.import_module("backend.routers.collections.maintenance_routes")
    monkeypatch.setattr(router_module.BlobNormalizer, "normalize", staticmethod(lambda blob: {}))
    monkeypatch.setattr(
        router_module.PipelineBlobValidator, "validate", classmethod(lambda cls, blob: None)
    )
    collection = SimpleNamespace(id=COLLECTION_ID, job_timeout_seconds=None, pipeline={})
    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=collection))
    monkeypatch.setattr(CONTEXT.database.collections, "get_schema", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        CONTEXT.database.documents, "resolve_query_ids", AsyncMock(return_value=[uuid.uuid4()])
    )


def test_bulk_reingest_with_missing_vectors_is_409_required(
    client, monkeypatch, real_rebuild_guards
) -> None:
    from backend.context import CONTEXT

    _patch_bulk(monkeypatch)
    reingest = AsyncMock()
    monkeypatch.setattr(
        CONTEXT.database.index_rebuild, "active_rebuild", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        CONTEXT.database.index_state,
        "missing",
        AsyncMock(return_value=[("topic", "meta_topic_dense")]),
    )
    monkeypatch.setattr(CONTEXT.database.ingestion, "reingest", reingest)

    response = client.post(f"/api/v1/collections/{COLLECTION_ID}/reingest", json={})

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "rebuild_index_required"
    assert detail["missing_vectors"] == ["meta_topic_dense"]
    reingest.assert_not_awaited()


def test_bulk_reingest_during_rebuild_is_409_active(
    client, monkeypatch, real_rebuild_guards
) -> None:
    from backend.context import CONTEXT

    _patch_bulk(monkeypatch)
    monkeypatch.setattr(
        CONTEXT.database.index_rebuild,
        "active_rebuild",
        AsyncMock(return_value=SimpleNamespace(id=JOB_ID)),
    )

    response = client.post(f"/api/v1/collections/{COLLECTION_ID}/reingest", json={})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "rebuild_index_active"


def test_search_hint_names_the_rebuild_route() -> None:
    from backend.libs.search import target_validator

    assert "/rebuild-index" in target_validator._REBUILD_HINT
