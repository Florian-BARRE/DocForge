"""Search router — the late-interaction (ColBERT) decision. The flag resolves request-over-config,
and it must actually change what reaches the facade: on + a ColBERT-capable embedder passes a
colbert query vector; off passes colbert=None (the untouched single-stage path); on + a collection
never ingested with ColBERT degrades gracefully to standard hybrid with a debug_info note (no 500).
Stores and the embedder are mocked — no network, no live stack."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shared_libs.services.db.facades import SearchHit


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


def _chunk() -> SimpleNamespace:
    return SimpleNamespace(
        id="11111111-1111-1111-1111-000000000001",
        document_id="22222222-2222-2222-2222-222222222222",
        text="chunk text",
        chunk_index=1,
        token_count=11,
    )


class _ColbertEmbedder:
    """A ColBERT-capable embedder stand-in — dense/sparse plus a token matrix."""

    def __init__(self, blob) -> None:
        self.blob = blob

    async def embed(self, query: str):
        return [0.1, 0.2, 0.3], None

    def wants_colbert(self) -> bool:
        return True

    async def embed_colbert(self, query: str):
        return [[0.9, 0.8], [0.7, 0.6]]


class _NoColbertEmbedder(_ColbertEmbedder):
    """A collection never ingested with ColBERT — its embedder emits none."""

    def wants_colbert(self) -> bool:
        return False


COLLECTION_ID = "33333333-3333-3333-3333-333333333333"
URL = f"/api/v1/collections/{COLLECTION_ID}/search"


@pytest.fixture
def wired(fastapi_app, monkeypatch):
    """Patch the stores; return (hybrid mock, collection) so a test can tune search config."""
    from backend.context import CONTEXT

    collection = SimpleNamespace(pipeline=_pipeline_with_embed(), search={})
    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=collection))
    monkeypatch.setattr(CONTEXT.database.collections, "get_schema", AsyncMock(return_value=[]))
    hybrid = AsyncMock(return_value=[SearchHit(chunk=_chunk(), score=0.5)])
    monkeypatch.setattr(CONTEXT.database.search, "hybrid", hybrid)
    return hybrid, collection


def _patch_embedder(monkeypatch, embedder_cls) -> None:
    from backend.routers.search import router as search_module

    monkeypatch.setattr(search_module, "QueryEmbedder", embedder_cls)


def test_request_flag_on_sends_colbert_and_pool_to_facade(client, wired, monkeypatch) -> None:
    """use_late_interaction=True + a ColBERT embedder ⇒ facade gets the colbert vector + pool."""
    _patch_embedder(monkeypatch, _ColbertEmbedder)
    hybrid, _ = wired

    response = client.post(URL, json={"query": "q", "use_late_interaction": True, "rescore_pool_size": 55})
    assert response.status_code == 200, response.text

    kwargs = hybrid.await_args.kwargs
    assert kwargs["colbert"] == [[0.9, 0.8], [0.7, 0.6]]
    assert kwargs["rescore_pool_size"] == 55
    assert response.json()["debug_info"] is None


def test_flag_off_passes_colbert_none(client, wired, monkeypatch) -> None:
    """use_late_interaction=False ⇒ the single-stage path: colbert kwarg is None."""
    _patch_embedder(monkeypatch, _ColbertEmbedder)
    hybrid, _ = wired

    response = client.post(URL, json={"query": "q", "use_late_interaction": False})
    assert response.status_code == 200, response.text
    assert hybrid.await_args.kwargs["colbert"] is None


def test_flag_defaults_to_collection_search_config(client, wired, monkeypatch) -> None:
    """None on the request defers to collection.search — on there ⇒ colbert flows."""
    _patch_embedder(monkeypatch, _ColbertEmbedder)
    hybrid, collection = wired
    collection.search = {"use_late_interaction": True, "rescore_pool_size": 33}

    response = client.post(URL, json={"query": "q"})  # no request flag
    assert response.status_code == 200, response.text
    kwargs = hybrid.await_args.kwargs
    assert kwargs["colbert"] == [[0.9, 0.8], [0.7, 0.6]]
    assert kwargs["rescore_pool_size"] == 33


def test_graceful_guard_degrades_without_colbert_vectors(client, wired, monkeypatch) -> None:
    """Flag on but the collection has no ColBERT vectors ⇒ standard hybrid + a debug note, no 500."""
    _patch_embedder(monkeypatch, _NoColbertEmbedder)
    hybrid, _ = wired

    response = client.post(URL, json={"query": "q", "use_late_interaction": True})
    assert response.status_code == 200, response.text
    assert hybrid.await_args.kwargs["colbert"] is None
    assert "late_interaction_skipped" in response.json()["debug_info"]
