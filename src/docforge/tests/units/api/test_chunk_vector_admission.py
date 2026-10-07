"""Upload + single-reingest admission refuse (409 ``rebuild_index_required``) BEFORE any job is minted
when the store lacks a chunk-scope semantic/lexical vector, and never read the store for a collection
without chunk-scope searchable fields. Facades + queue mocked.
"""

import importlib
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from shared_libs.public_models import FieldScope

COLLECTION_ID = uuid.uuid4()


def _field(name: str, scope: FieldScope, *, semantic: bool = False, lexical: bool = False):
    return SimpleNamespace(field_name=name, scope=scope, semantic=semantic, lexical=lexical)


def _patch_store(monkeypatch, schema: list, missing: list) -> AsyncMock:
    from backend.context import CONTEXT

    monkeypatch.setattr(
        CONTEXT.database.index_rebuild, "active_rebuild", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(CONTEXT.database.collections, "get_schema", AsyncMock(return_value=schema))
    missing_for = AsyncMock(return_value=missing)
    monkeypatch.setattr(CONTEXT.database.index_state, "missing_for", missing_for)
    return missing_for


def _patch_upload(monkeypatch) -> None:
    from backend.context import CONTEXT

    collection = SimpleNamespace(
        id=COLLECTION_ID, pipeline={}, supported_formats=None, max_file_size_mb=None
    )
    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=collection))
    router_module = importlib.import_module("backend.routers.documents.router")
    monkeypatch.setattr(router_module.BlobNormalizer, "normalize", staticmethod(lambda blob: {}))
    monkeypatch.setattr(
        router_module.PipelineBlobValidator, "validate", classmethod(lambda cls, blob: None)
    )


def _upload(client):
    return client.post(
        "/api/v1/documents",
        files={"file": ("a.md", b"# hello\n", "text/markdown")},
        data={"collection_id": str(COLLECTION_ID)},
    )


def test_upload_with_undeclared_chunk_vector_is_409_required(
    client, monkeypatch, real_rebuild_guards
) -> None:
    from backend.context import CONTEXT

    _patch_upload(monkeypatch)
    missing_for = _patch_store(
        monkeypatch,
        [_field("topic", FieldScope.CHUNK, semantic=True), _field("author", FieldScope.DOCUMENT)],
        [("topic", "meta_topic_dense")],
    )
    admit = AsyncMock()
    monkeypatch.setattr(CONTEXT.database.ingestion, "admit", admit)

    response = _upload(client)

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "rebuild_index_required"
    assert detail["missing_fields"] == ["topic"]
    assert detail["missing_vectors"] == ["meta_topic_dense"]
    missing_for.assert_awaited_once_with(COLLECTION_ID, ["topic"], [])
    admit.assert_not_awaited()


def test_single_reingest_with_undeclared_chunk_vector_is_409_required(
    client, monkeypatch, real_rebuild_guards
) -> None:
    from backend.context import CONTEXT

    document = SimpleNamespace(id=uuid.uuid4(), collection_id=COLLECTION_ID)
    monkeypatch.setattr(CONTEXT.database.documents, "get", AsyncMock(return_value=document))
    _patch_store(
        monkeypatch,
        [_field("nom", FieldScope.CHUNK, lexical=True)],
        [("nom", "meta_nom_bm25")],
    )
    reingest = AsyncMock()
    monkeypatch.setattr(CONTEXT.database.ingestion, "reingest", reingest)

    response = client.post(f"/api/v1/documents/{document.id}/reingest")

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "rebuild_index_required"
    assert "nom" in detail["detail"]
    reingest.assert_not_awaited()


async def test_no_store_call_without_chunk_scope_searchable_fields(monkeypatch) -> None:
    from backend.context import CONTEXT
    from backend.libs.index_rebuild.guards import IndexRebuildGuards

    missing_for = _patch_store(
        monkeypatch,
        [
            _field("author", FieldScope.DOCUMENT, semantic=True, lexical=True),
            _field("tag", FieldScope.CHUNK),
        ],
        [("author", "meta_author_dense")],
    )

    await IndexRebuildGuards.assert_chunk_vectors_declared(CONTEXT.database, COLLECTION_ID)

    missing_for.assert_not_awaited()
