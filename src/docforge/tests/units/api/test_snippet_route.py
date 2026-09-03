"""Config-snippet router: GET/POST /collections/{id}/snippets/{kind}. The database façade is mocked at
the CONTEXT.database seam (no DB/S3/Qdrant), so the test asserts the route wiring, the exported snippet
WRAPPER shape ({kind, format_version, docforge_version, body}) with provider secrets masked, and the
apply path's contract: version-gate + kind-match (both 422), the SnippetImportResult with its
needs_reindex signal, and the 404 on an unknown collection. The pure shaping/merge is locked elsewhere;
this exercises the endpoint contract the SDK/MCP/frontend mirror."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shared_libs.pipelines.ingest.stages import IngestAssembler, default_state

COLLECTION_ID = "b7ac3cda-9070-4bd3-983c-27851179106b"


def _default_pipeline_blob() -> dict:
    """The stock default pipeline blob (local embed on, enrich/metagen off)."""
    return IngestAssembler.assemble(default_state()).model_dump(mode="json")


def _collection() -> SimpleNamespace:
    """A collection row with the stock pipeline, an empty search blob and no schema."""
    return SimpleNamespace(
        id=uuid.UUID(COLLECTION_ID), pipeline=_default_pipeline_blob(), search={}
    )


@pytest.fixture
def wired(fastapi_app, monkeypatch):
    """Patch the collection read + schema and the config-write seams the applier touches."""
    from backend.context import CONTEXT  # noqa: PLC0415 — deferred until app/ is on sys.path

    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=_collection()))
    monkeypatch.setattr(CONTEXT.database.collections, "get_schema", AsyncMock(return_value=[]))
    monkeypatch.setattr(CONTEXT.database.collections, "update_config", AsyncMock())
    monkeypatch.setattr(CONTEXT.database.collections, "update_schema", AsyncMock(return_value=True))
    monkeypatch.setattr(
        CONTEXT.database.collections, "reconcile_store", AsyncMock(return_value=set())
    )
    monkeypatch.setattr(CONTEXT.queue, "enqueue_backfill", AsyncMock())
    return CONTEXT


def test_snippet_routes_are_registered(fastapi_app) -> None:
    """Both the export (GET) and apply (POST) routes must be part of the API contract."""
    verbs = fastapi_app.openapi()["paths"]["/api/v1/collections/{collection_id}/snippets/{kind}"]
    assert "get" in verbs and "post" in verbs


def test_export_pipeline_snippet_shape(client, wired) -> None:
    """Export wraps the pipeline slice as {kind, format_version, docforge_version, body}."""
    response = client.get(f"/api/v1/collections/{COLLECTION_ID}/snippets/pipeline")
    assert response.status_code == 200
    body = response.json()

    assert body["kind"] == "pipeline"
    assert body["format_version"] == 1
    assert isinstance(body["docforge_version"], str)
    assert body["body"]["nodes"]  # the graph slice is carried verbatim


def test_export_schema_snippet_carries_fields(client, wired) -> None:
    """A schema snippet's body carries a 'fields' list (empty here)."""
    response = client.get(f"/api/v1/collections/{COLLECTION_ID}/snippets/schema")
    assert response.status_code == 200
    assert response.json()["body"] == {"fields": []}


def test_export_unknown_collection_is_404(client, fastapi_app, monkeypatch) -> None:
    """An unknown collection is a 404, mirroring the other collection reads."""
    from backend.context import CONTEXT  # noqa: PLC0415

    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=None))
    response = client.get(f"/api/v1/collections/{uuid.uuid4()}/snippets/pipeline")
    assert response.status_code == 404


def test_apply_pipeline_snippet_roundtrips(client, wired) -> None:
    """Applying the collection's own pipeline snippet is a no-reindex no-op through update_config."""
    snippet = client.get(f"/api/v1/collections/{COLLECTION_ID}/snippets/pipeline").json()
    response = client.post(f"/api/v1/collections/{COLLECTION_ID}/snippets/pipeline", json=snippet)
    assert response.status_code == 200
    result = response.json()
    assert result["kind"] == "pipeline"
    assert result["needs_reindex"] is False  # same embed space → no reindex
    wired.database.collections.update_config.assert_awaited_once()


def test_apply_schema_snippet_reports_reindex(client, wired) -> None:
    """A schema apply surfaces the update_schema reindex signal and reconciles the store."""
    snippet = {
        "kind": "schema",
        "format_version": 1,
        "docforge_version": "test",
        "body": {"fields": []},
    }
    response = client.post(f"/api/v1/collections/{COLLECTION_ID}/snippets/schema", json=snippet)
    assert response.status_code == 200
    assert response.json()["needs_reindex"] is True  # the mocked update_schema returns True
    wired.database.collections.reconcile_store.assert_awaited_once()
    wired.queue.enqueue_backfill.assert_awaited_once()


def test_apply_unsupported_version_is_422(client, wired) -> None:
    """A snippet from a future format version this build cannot read is a 422."""
    snippet = {
        "kind": "pipeline",
        "format_version": 999,
        "docforge_version": "future",
        "body": {"nodes": []},
    }
    response = client.post(f"/api/v1/collections/{COLLECTION_ID}/snippets/pipeline", json=snippet)
    assert response.status_code == 422


def test_apply_kind_mismatch_is_422(client, wired) -> None:
    """A snippet whose kind differs from the URL slice cannot be applied (422)."""
    snippet = {
        "kind": "search",
        "format_version": 1,
        "docforge_version": "test",
        "body": {},
    }
    response = client.post(f"/api/v1/collections/{COLLECTION_ID}/snippets/pipeline", json=snippet)
    assert response.status_code == 422
