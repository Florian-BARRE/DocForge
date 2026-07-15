"""Search router: the query-to-hits wiring with the graph-based search pipeline mocked out at the
CONTEXT.search_service seam. Asserts the route stays the request-side gate (404 / 409 / 422 ladder),
resolves the query knobs, DELEGATES retrieval to the search service with the right arguments, and
flattens the graph's Hits (chunk_index/token_count lifted out of Hit.metadata) into the client
response. No network, no live stack, no hand-rolled facade retrieval."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shared_libs.public_models.search import Hit, SearchResult


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


def _result(query: str) -> SearchResult:
    """A one-hit SearchResult; chunk_index/token_count ride in Hit.metadata (as the graph emits)."""
    return SearchResult(
        query=query,
        hits=[
            Hit(
                chunk_id="11111111-1111-1111-1111-000000000001",
                document_id="22222222-2222-2222-2222-222222222222",
                score=0.42,
                rank=1,
                text="chunk text 1",
                metadata={"chunk_index": 3, "token_count": 42},
            )
        ],
    )


@pytest.fixture
def wired(fastapi_app, monkeypatch):
    """Patch the collection reads + the search service; return the captured search() mock."""
    from backend.context import CONTEXT

    collection = SimpleNamespace(pipeline=_pipeline_with_embed(), search={})
    monkeypatch.setattr(
        CONTEXT.database.collections, "get", AsyncMock(return_value=collection)
    )
    monkeypatch.setattr(
        CONTEXT.database.collections, "get_schema", AsyncMock(return_value=_schema())
    )
    search = AsyncMock(side_effect=lambda _cid, query, **_kw: _result(query))
    monkeypatch.setattr(CONTEXT.search_service, "search", search)
    return search


def test_search_route_is_registered(fastapi_app) -> None:
    """The search route must be part of the API contract (POST under the collection scope)."""
    paths = fastapi_app.openapi()["paths"]
    assert "post" in paths["/api/v1/collections/{collection_id}/search"]


def test_search_delegates_to_service_and_shapes_hits(client, wired) -> None:
    """Happy path: the service is called with resolved knobs, and the graph Hit is flattened."""
    # 1. A query with a scalar filter on the filterable field.
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "how does it work", "limit": 5, "filters": {"topic": "ai"}},
    )
    assert response.status_code == 200, response.text

    # 2. Retrieval was delegated to the search service with the resolved arguments.
    kwargs = wired.await_args.kwargs
    assert wired.await_args.args[1] == "how does it work"
    assert kwargs["top_k"] == 5
    assert kwargs["filters"] == {"topic": "ai"}
    assert kwargs["use_late_interaction"] is False
    # collection.search is a topology blob now, not a tuning dict — with no request override the
    # router forwards None and the retrieve node's own config / the store default governs.
    assert kwargs["rescore_pool_size"] is None

    # 3. The hit is the flat view of the graph Hit (index/tokens lifted out of metadata).
    hit = response.json()["hits"][0]
    assert hit["chunk_id"] == "11111111-1111-1111-1111-000000000001"
    assert hit["document_id"] == "22222222-2222-2222-2222-222222222222"
    assert hit["score"] == 0.42
    assert hit["text"] == "chunk text 1"
    assert hit["chunk_index"] == 3
    assert hit["token_count"] == 42


def test_search_passes_list_filter_verbatim(client, wired) -> None:
    """A list filter value reaches the service unchanged — the graph trusts the filter map."""
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "q", "filters": {"topic": ["ai", "ml"]}},
    )
    assert response.status_code == 200, response.text
    assert wired.await_args.kwargs["filters"] == {"topic": ["ai", "ml"]}


def test_search_non_filterable_field_is_422(client, wired) -> None:
    """A filter on a non-filterable field is rejected before the service is invoked."""
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "q", "filters": {"note": "x"}},
    )
    assert response.status_code == 422, response.text
    wired.assert_not_awaited()


def test_search_blank_query_is_422(client, wired) -> None:
    """A whitespace-only query is rejected before it reaches the service."""
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


def test_search_invalid_stored_graph_is_422_not_500(client, wired, monkeypatch) -> None:
    """A stored search graph that the runner rejects (SearchRunError) is mapped to a clean 422 at
    the HTTP boundary — never a 500 with a traceback."""
    from backend.context import CONTEXT
    from backend.libs.search import SearchRunError

    monkeypatch.setattr(
        CONTEXT.search_service,
        "search",
        AsyncMock(side_effect=SearchRunError("final node produced RankedHits")),
    )
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "q"},
    )
    # 1. The invalid stored graph surfaces as a 422 naming the stored search graph, not a 500.
    assert response.status_code == 422, response.text
    assert "stored search graph is invalid" in response.text


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
