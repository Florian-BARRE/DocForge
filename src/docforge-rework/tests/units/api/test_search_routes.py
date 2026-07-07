"""Search router: the query-to-hits wiring with the stores and the embedder mocked out. Asserts the
route embeds via the collection's embedder, names the query vectors with the persistence constants
(content_dense / content_bm25), maps filters to typed Conditions over the filterable fields, and
shapes the hydrated hits — plus the 404 / 409 / 422 rejection ladder. No network, no live stack."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shared_libs.services.db.facades import SearchHit
from shared_libs.services.db.qdrant import Match, MatchAny, SparseVec, VectorNames


# A minimal pipeline blob carrying one embed action node (bge_server, sparse on).
def _pipeline_with_embed() -> dict:
    return {
        "node_type": "group",
        "id": "root",
        "nodes": [
            {
                "node_type": "action",
                "id": "embed",
                "family": "embed",
                "kind": "bge_server",
                "config": {"model": "BAAI/bge-m3", "base_url": "http://bge:8008"},
            }
        ],
        "transitions": [],
        "bindings": {},
    }


def _schema() -> list:
    """One filterable field ('topic') + one non-filterable ('note')."""
    return [
        SimpleNamespace(field_name="topic", filterable=True),
        SimpleNamespace(field_name="note", filterable=False),
    ]


def _chunk(index: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=f"11111111-1111-1111-1111-00000000000{index}",
        document_id="22222222-2222-2222-2222-222222222222",
        text=f"chunk text {index}",
        chunk_index=index,
        token_count=10 + index,
    )


class _FakeEmbedder:
    """Stands in for QueryEmbedder — returns fixed vectors, no HTTP."""

    def __init__(self, blob) -> None:
        self.blob = blob

    async def embed(self, query: str):
        return [0.1, 0.2, 0.3], SparseVec(indices=[7], values=[0.9])


@pytest.fixture
def wired(fastapi_app, monkeypatch):
    """Patch CONTEXT stores + the embedder; return the captured hybrid() call kwargs."""
    from backend.context import CONTEXT
    from backend.routers.search import router as search_module

    collection = SimpleNamespace(pipeline=_pipeline_with_embed())
    monkeypatch.setattr(
        CONTEXT.database.collections, "get", AsyncMock(return_value=collection)
    )
    monkeypatch.setattr(
        CONTEXT.database.collections, "get_schema", AsyncMock(return_value=_schema())
    )
    hybrid = AsyncMock(return_value=[SearchHit(chunk=_chunk(1), score=0.42)])
    monkeypatch.setattr(CONTEXT.database.search, "hybrid", hybrid)
    monkeypatch.setattr(search_module, "QueryEmbedder", _FakeEmbedder)
    return hybrid


def test_search_route_is_registered(fastapi_app) -> None:
    """The search route must be part of the API contract (POST under the collection scope)."""
    paths = fastapi_app.openapi()["paths"]
    assert "post" in paths["/api/v1/collections/{collection_id}/search"]


def test_search_builds_named_vectors_conditions_and_hits(client, wired) -> None:
    """Happy path: content vectors named by the constants, a Match filter, and a shaped hit."""
    # 1. A query with a scalar filter on the filterable field.
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "how does it work", "limit": 5, "filters": {"topic": "ai"}},
    )
    assert response.status_code == 200, response.text

    # 2. The facade was called with the persistence-side vector names.
    kwargs = wired.await_args.kwargs
    assert set(kwargs["dense"]) == {VectorNames.CONTENT_DENSE}
    assert set(kwargs["sparse"]) == {VectorNames.CONTENT_SPARSE}
    assert kwargs["dense"][VectorNames.CONTENT_DENSE] == [0.1, 0.2, 0.3]
    assert kwargs["limit"] == 5

    # 3. The scalar filter became a typed exact-match Condition.
    conditions = kwargs["conditions"]
    assert conditions == [Match(field="topic", value="ai")]

    # 4. The hit is the flat view of the hydrated SearchHit.
    hit = response.json()["hits"][0]
    assert hit["chunk_id"] == "11111111-1111-1111-1111-000000000001"
    assert hit["document_id"] == "22222222-2222-2222-2222-222222222222"
    assert hit["score"] == 0.42
    assert hit["text"] == "chunk text 1"


def test_search_list_filter_becomes_match_any(client, wired) -> None:
    """A list filter value maps to a set-membership (any-of) Condition."""
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "q", "filters": {"topic": ["ai", "ml"]}},
    )
    assert response.status_code == 200, response.text
    conditions = wired.await_args.kwargs["conditions"]
    assert conditions == [MatchAny(field="topic", values=["ai", "ml"])]


def test_search_non_filterable_field_is_422(client, wired) -> None:
    """A filter on a non-filterable field is rejected before any vector search."""
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "q", "filters": {"note": "x"}},
    )
    assert response.status_code == 422, response.text
    wired.assert_not_awaited()


def test_search_blank_query_is_422(client, wired) -> None:
    """A whitespace-only query is rejected before it reaches the embedder."""
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "   "},
    )
    assert response.status_code == 422, response.text
    wired.assert_not_awaited()


def test_search_unknown_collection_is_404(client, fastapi_app, monkeypatch) -> None:
    """An unknown collection id is an explicit 404."""
    from backend.context import CONTEXT

    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=None))
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "q"},
    )
    assert response.status_code == 404, response.text


def test_search_no_embed_node_is_409(client, fastapi_app, monkeypatch) -> None:
    """A collection whose pipeline has no embed node cannot be searched (409)."""
    from backend.context import CONTEXT

    collection = SimpleNamespace(
        pipeline={"node_type": "group", "id": "root", "nodes": [], "transitions": [], "bindings": {}}
    )
    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=collection))
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "q"},
    )
    assert response.status_code == 409, response.text
