"""Finding D5 — a field flagged semantic/lexical in Postgres but whose named vector the Qdrant store
never declared (Qdrant cannot add a vector to a live collection) must be reported honestly: the search
target gate 422s with the rebuild hint (instead of Qdrant's misleading "invalid search graph"), the
collection detail exposes ``missing_vectors`` and the PATCH response folds the store gap into
``schema_diff.reindex_required_fields``. ``from backend...`` deferred until fastapi_app registered app/."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from qdrant_client.http.exceptions import UnexpectedResponse

from shared_libs.public_models import FieldType
from shared_libs.public_models.search import SearchResult
from shared_libs.services.db.facades import IndexStateFacade
from shared_libs.services.db.qdrant import QdrantCollectionApi

_EMBED_PIPELINE = {
    "kind": "group",
    "id": "root",
    "nodes": [
        {
            "kind": "bge_server",
            "family": "embed",
            "id": "embed",
            "config": {"base_url": "http://bge_server:8080", "embed_sparse": True},
        }
    ],
    "transitions": [],
    "bindings": {},
}


def _schema() -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            field_name="title",
            field_type=FieldType.STRING,
            filterable=False,
            semantic=True,
            lexical=True,
        )
    ]


# --------------------------------------------------------------------------- #
# QdrantCollectionApi.missing_vectors — the shared pure rule
# --------------------------------------------------------------------------- #
def test_missing_vectors_pairs_each_flagged_field_with_its_undeclared_vector() -> None:
    missing = QdrantCollectionApi.missing_vectors(
        ["title", "author"], ["title"], {"content_dense", "meta_author_dense"}, {"content_bm25"}
    )
    assert missing == [("title", "meta_title_bm25"), ("title", "meta_title_dense")]


def test_missing_vectors_is_empty_when_every_vector_is_declared() -> None:
    assert (
        QdrantCollectionApi.missing_vectors(["a"], ["a"], {"meta_a_dense"}, {"meta_a_bm25"}) == []
    )


# --------------------------------------------------------------------------- #
# IndexStateFacade — one Qdrant call; a never-ingested collection declares nothing
# --------------------------------------------------------------------------- #
async def test_declared_vectors_reads_the_named_vector_maps() -> None:
    qdrant = MagicMock()
    params = SimpleNamespace(vectors={"content_dense": 1}, sparse_vectors={"content_bm25": 1})
    qdrant.raw.get_collection = AsyncMock(
        return_value=SimpleNamespace(config=SimpleNamespace(params=params))
    )
    facade = IndexStateFacade(MagicMock(), qdrant)
    assert await facade.declared_vectors(uuid.uuid4()) == ({"content_dense"}, {"content_bm25"})


async def test_declared_vectors_is_none_without_a_qdrant_space() -> None:
    qdrant = MagicMock()
    qdrant.raw.get_collection = AsyncMock(
        side_effect=UnexpectedResponse(404, "Not Found", b"", MagicMock())
    )
    facade = IndexStateFacade(MagicMock(), qdrant)
    assert await facade.declared_vectors(uuid.uuid4()) is None
    assert await facade.missing_for(uuid.uuid4(), ["title"], ["title"]) == []


# --------------------------------------------------------------------------- #
# SearchTargetValidator — flags alone are not enough
# --------------------------------------------------------------------------- #
def _target(**kwargs):
    from backend.routers.search.models import SearchTargetModel  # noqa: PLC0415

    return SearchTargetModel(**kwargs)


def test_flagged_but_undeclared_vector_is_an_error_with_the_rebuild_hint(fastapi_app) -> None:
    from backend.libs.search import SearchTargetValidator  # noqa: PLC0415

    declared = ({"content_dense"}, {"content_bm25"})
    errors = SearchTargetValidator.validate_search_targets(
        [_target(field="title", semantic=True, lexical=True)], _schema(), declared
    )
    assert len(errors) == 2
    assert "field 'title' has no indexed semantic vector" in errors[0]
    assert "field 'title' has no indexed lexical vector" in errors[1]
    assert all("rebuild_index" in error for error in errors)


def test_declared_vector_passes_and_no_space_is_not_checked(fastapi_app) -> None:
    from backend.libs.search import SearchTargetValidator  # noqa: PLC0415

    targets = [_target(field="title", semantic=True)]
    declared = ({"content_dense", "meta_title_dense"}, set())
    assert SearchTargetValidator.validate_search_targets(targets, _schema(), declared) == []
    assert SearchTargetValidator.validate_search_targets(targets, _schema(), None) == []


def test_store_check_is_only_needed_for_metadata_targets(fastapi_app) -> None:
    from backend.libs.search import SearchTargetValidator  # noqa: PLC0415

    assert not SearchTargetValidator.needs_store_check(None)
    assert not SearchTargetValidator.needs_store_check([_target(field="content", semantic=True)])
    assert SearchTargetValidator.needs_store_check([_target(field="title", semantic=True)])


# --------------------------------------------------------------------------- #
# The search route — 422 with the hint, never reaching the search service
# --------------------------------------------------------------------------- #
@pytest.fixture
def search_wired(fastapi_app, monkeypatch):
    from backend.context import CONTEXT  # noqa: PLC0415

    collection = SimpleNamespace(pipeline=_EMBED_PIPELINE, search={})
    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=collection))
    monkeypatch.setattr(
        CONTEXT.database.collections, "get_schema", AsyncMock(return_value=_schema())
    )
    declared = AsyncMock(return_value=({"content_dense"}, {"content_bm25"}))
    monkeypatch.setattr(CONTEXT.database.index_state, "declared_vectors", declared)
    search = AsyncMock(return_value=(SearchResult(query="q", hits=[]), (0, 0, None, 0)))
    monkeypatch.setattr(CONTEXT.search_service, "search", search)
    return SimpleNamespace(declared=declared, search=search)


def test_search_on_an_undeclared_vector_is_422_with_the_rebuild_hint(client, search_wired) -> None:
    body = {"query": "q", "search_in": [{"field": "title", "semantic": True}]}
    response = client.post(f"/api/v1/collections/{uuid.uuid4()}/search", json=body)
    assert response.status_code == 422, response.text
    assert "no indexed semantic vector" in response.json()["detail"]
    assert "rebuild_index" in response.json()["detail"]
    search_wired.search.assert_not_awaited()


def test_content_only_search_never_reads_the_store(client, search_wired) -> None:
    response = client.post(f"/api/v1/collections/{uuid.uuid4()}/search", json={"query": "q"})
    assert response.status_code == 200, response.text
    search_wired.declared.assert_not_awaited()


# --------------------------------------------------------------------------- #
# Collection detail + PATCH response — the store gap is surfaced
# --------------------------------------------------------------------------- #
def test_update_response_folds_the_store_gap_into_reindex_required_fields(fastapi_app) -> None:
    from backend.libs.schema_ops import SchemaDiff  # noqa: PLC0415
    from backend.routers.collections.helpers import CollectionHelpers  # noqa: PLC0415

    collection = SimpleNamespace(
        id=uuid.uuid4(),
        name="c",
        supported_formats=["md"],
        tags=[],
        max_file_size_bytes=1,
        job_timeout_seconds=None,
        trace_verbosity="shape",
        needs_reindex=True,
        created_at=None,
        pipeline={},
        search={},
        title_field=None,
        estimate_overrides=None,
    )
    schema = SimpleNamespace(diff=SchemaDiff(reindex_required_fields=["other"]))
    response = CollectionHelpers.to_update_response(
        collection, [], schema, False, [("title", "meta_title_dense")]
    )
    assert response.missing_vectors == ["meta_title_dense"]
    assert response.schema_diff.reindex_required_fields == ["other", "title"]
    # The resolved patch's own diff is never mutated by the response mapping.
    assert schema.diff.reindex_required_fields == ["other"]
