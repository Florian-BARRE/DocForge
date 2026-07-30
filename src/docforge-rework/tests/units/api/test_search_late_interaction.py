"""Search router — the late-interaction (ColBERT) decision after the cutover to the graph-based
search pipeline. The flag resolves request-over-config and is forwarded to CONTEXT.search_service
(the graph encodes the query, so the router no longer embeds). The router keeps ONLY the capability
check: on + a ColBERT-capable embedder ⇒ the flag flows and debug_info is None; on + a collection
never ingested with ColBERT ⇒ still forwarded but a debug_info note is surfaced (graceful, no 500).
The search service is mocked — no network, no live stack."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shared_libs.public_models.search import Hit, SearchResult


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


def _result(query: str) -> SearchResult:
    return SearchResult(
        query=query,
        hits=[
            Hit(
                chunk_id="11111111-1111-1111-1111-000000000001",
                document_id="22222222-2222-2222-2222-222222222222",
                score=0.5,
                rank=1,
                text="chunk text",
                metadata={"chunk_index": 1, "token_count": 11},
            )
        ],
    )


class _ColbertEmbedder:
    """A ColBERT-capable embedder stand-in — only the capability check is exercised now."""

    def __init__(self, blob) -> None:
        self.blob = blob

    def wants_colbert(self) -> bool:
        return True


class _NoColbertEmbedder(_ColbertEmbedder):
    """A collection never ingested with ColBERT — its embedder emits none."""

    def wants_colbert(self) -> bool:
        return False


COLLECTION_ID = "33333333-3333-3333-3333-333333333333"
URL = f"/api/v1/collections/{COLLECTION_ID}/search"


@pytest.fixture
def wired(fastapi_app, monkeypatch):
    """Patch the collection reads + the search service; return (search mock, collection)."""
    from backend.context import CONTEXT

    collection = SimpleNamespace(pipeline=_pipeline_with_embed(), search={})
    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=collection))
    monkeypatch.setattr(CONTEXT.database.collections, "get_schema", AsyncMock(return_value=[]))
    search = AsyncMock(side_effect=lambda _cid, query, **_kw: _result(query))
    monkeypatch.setattr(CONTEXT.search_service, "search", search)
    return search, collection


def _patch_embedder(monkeypatch, embedder_cls) -> None:
    from backend.routers.search import router as search_module

    monkeypatch.setattr(search_module, "QueryEmbedder", embedder_cls)


def test_request_flag_on_forwards_late_interaction_and_pool(client, wired, monkeypatch) -> None:
    """use_late_interaction=True + a ColBERT embedder ⇒ the service gets the flag + pool, no note."""
    _patch_embedder(monkeypatch, _ColbertEmbedder)
    search, _ = wired

    response = client.post(
        URL, json={"query": "q", "use_late_interaction": True, "rescore_pool_size": 55}
    )
    assert response.status_code == 200, response.text

    kwargs = search.await_args.kwargs
    assert kwargs["use_late_interaction"] is True
    assert kwargs["rescore_pool_size"] == 55
    assert response.json()["debug_info"] is None


def test_flag_off_forwards_false(client, wired, monkeypatch) -> None:
    """use_late_interaction=False ⇒ the flag is forwarded off to the service."""
    _patch_embedder(monkeypatch, _ColbertEmbedder)
    search, _ = wired

    response = client.post(URL, json={"query": "q", "use_late_interaction": False})
    assert response.status_code == 200, response.text
    assert search.await_args.kwargs["use_late_interaction"] is False


def test_knobs_come_from_the_request_only(client, wired, monkeypatch) -> None:
    """collection.search is a topology blob now, not a tuning dict — with no request flag the
    router forwards off / None, whatever the stored blob contains (the retrieve node's own config /
    the store default governs the pool)."""
    _patch_embedder(monkeypatch, _ColbertEmbedder)
    search, collection = wired
    # A stored search GRAPH blob (has "nodes") — must NOT be mined for tuning knobs.
    collection.search = {
        "id": "custom",
        "nodes": [{"id": "n", "family": "query", "kind": "normalize"}],
    }

    response = client.post(URL, json={"query": "q"})  # no request flag
    assert response.status_code == 200, response.text
    kwargs = search.await_args.kwargs
    assert kwargs["use_late_interaction"] is False
    assert kwargs["rescore_pool_size"] is None


def test_graceful_guard_degrades_without_colbert_vectors(client, wired, monkeypatch) -> None:
    """Flag on but the collection has no ColBERT vectors ⇒ a debug note, still forwarded, no 500."""
    _patch_embedder(monkeypatch, _NoColbertEmbedder)
    search, _ = wired

    response = client.post(URL, json={"query": "q", "use_late_interaction": True})
    assert response.status_code == 200, response.text
    assert search.await_args.kwargs["use_late_interaction"] is True
    assert "late_interaction_skipped" in response.json()["debug_info"]
