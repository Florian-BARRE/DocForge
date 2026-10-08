"""The ``(embed, dense_sparse)`` node end to end with HTTP mocked: the three modes (dense only, sparse
only, dense + sparse), the ONE combined ``/embed_all`` per batch when both slots are the same
bge_server, two independent servers called separately, and the sparse IDF flag each sparse provider
dictates (``bm25_local`` → IDF, ``bge_server`` learned weights → none)."""

import json
import uuid

import httpx
import pytest

import shared_libs.pipelines.nodes  # noqa: F401 — auto-discovery
from shared_libs.pipelines.nodes.embed.base import EmbedConsumes
from shared_libs.pipelines.nodes.embed.dense_sparse import (
    EmbedDenseSparseConfig,
    EmbedDenseSparseNode,
)
from shared_libs.pipelines.nodes.http_pool import HttpClientPool
from shared_libs.public_models import Chunk, CollectionContract

CONTRACT = CollectionContract(
    collection_id=uuid.uuid4(), name="c", supported_formats=["md"], max_file_size_bytes=1, fields=[]
)
CHUNKS = [
    Chunk(chunk_id=f"d#c{n}", ordinal=n, text=text)
    for n, text in enumerate(
        ["Passation des marchés.", "Exécution des marchés.", "Cats purr.", "Dogs bark.", "Sun."]
    )
]
_BGE_A = {"kind": "bge_server", "base_url": "http://bge-a:80"}
_BGE_B = {"kind": "bge_server", "base_url": "http://bge-b:80"}


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, int]]:
    """Mock every bge route; record ``(host, path, batch size)`` per request."""
    recorded: list[tuple[str, str, int]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        inputs = json.loads(request.content)["inputs"]
        recorded.append((request.url.host, request.url.path, len(inputs)))
        dense = [[0.1] * 4 for _ in inputs]
        sparse = [[{"index": 3, "value": 0.7}] for _ in inputs]
        routes = {"/embed": dense, "/embed_sparse": sparse}
        if request.url.path == "/embed_all":
            return httpx.Response(200, json={"dense": dense, "sparse": sparse})
        if request.url.path in routes:
            return httpx.Response(200, json=routes[request.url.path])
        return httpx.Response(404)

    HttpClientPool.reset()
    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda *a, **k: original(*a, **{**k, "transport": transport})
    )
    yield recorded
    HttpClientPool.reset()


def _node(**slots: object) -> EmbedDenseSparseNode:
    return EmbedDenseSparseNode(id="e", config=EmbedDenseSparseConfig(batch_size=2, **slots))


async def _run(node: EmbedDenseSparseNode):
    return (await node.run(EmbedConsumes(chunks=CHUNKS, contract=CONTRACT))).embeddings


async def test_same_bge_on_both_slots_is_exactly_one_embed_all_per_batch(calls) -> None:
    node = _node(dense=_BGE_A, sparse={**_BGE_A, "base_url": "http://BGE-A:80/"})
    emb = await _run(node)

    assert node.combined()
    assert calls == [
        ("bge-a", "/embed_all", 2),
        ("bge-a", "/embed_all", 2),
        ("bge-a", "/embed_all", 1),
    ]
    assert all(item.dense and item.sparse and item.sparse.indices == [3] for item in emb.items)
    assert (emb.dense_enabled, emb.sparse_enabled, emb.sparse_idf) == (True, True, False)


async def test_default_config_is_the_combined_in_stack_bge(calls) -> None:
    node = EmbedDenseSparseNode(id="e", config=EmbedDenseSparseConfig())
    assert node.combined()
    assert node.probe_endpoints() == ["http://bge_server:80"]
    assert not node.sparse_idf()  # bge learned weights: no IDF modifier


async def test_two_bge_servers_are_called_separately_per_axis(calls) -> None:
    node = _node(dense=_BGE_A, sparse=_BGE_B)
    emb = await _run(node)

    assert not node.combined()
    assert {(host, path) for host, path, _ in calls} == {
        ("bge-a", "/embed"),
        ("bge-b", "/embed_sparse"),
    }
    assert len(calls) == 6  # 3 batches × 2 axes, never /embed_all
    assert sorted(node.probe_endpoints()) == ["http://bge-a:80", "http://bge-b:80"]
    assert all(item.dense and item.sparse for item in emb.items)


async def test_dense_only_mode_never_calls_a_sparse_route(calls) -> None:
    node = _node(dense=_BGE_A, sparse=None)
    emb = await _run(node)

    assert {path for _, path, _ in calls} == {"/embed"}
    assert all(item.dense and item.sparse is None for item in emb.items)
    assert (emb.dense_enabled, emb.sparse_enabled) == (True, False)


async def test_sparse_only_bm25_local_is_offline_and_idf(calls) -> None:
    node = _node(dense=None, sparse={"kind": "bm25_local"})
    emb = await _run(node)

    assert calls == []  # in-process encoder, no network
    assert node.probe_endpoints() == []
    assert node.sparse_idf()
    assert all(item.dense is None and item.sparse and item.sparse.indices for item in emb.items)
    assert (emb.dense_enabled, emb.sparse_enabled, emb.sparse_idf) == (False, True, True)


async def test_bge_dense_plus_bm25_local_sparse(calls) -> None:
    node = _node(dense=_BGE_A, sparse={"kind": "bm25_local"})
    emb = await _run(node)

    assert not node.combined()
    assert {path for _, path, _ in calls} == {"/embed"}
    assert emb.sparse_idf and all(item.dense and item.sparse for item in emb.items)


async def test_bm25_local_field_role_normalises_against_the_short_reference(calls) -> None:
    node = _node(dense=None, sparse={"kind": "bm25_local"})
    text = "Passation des marchés publics de travaux"
    content = (await node._embed_sparse([text]))[0]
    field = (await node._embed_sparse_fields([text]))[0]
    query = await node._embed_query_sparse("passation des marchés")

    assert content.indices == field.indices
    assert content.values != field.values  # content ref 256 vs field ref 8
    assert set(query.indices) <= set(field.indices)


def test_both_slots_off_is_rejected_at_config() -> None:
    with pytest.raises(ValueError, match="both slots are null"):
        EmbedDenseSparseConfig(dense=None, sparse=None)


def test_a_dense_only_kind_is_refused_in_the_sparse_slot() -> None:
    with pytest.raises(ValueError):
        EmbedDenseSparseConfig(sparse={"kind": "openai_compatible", "base_url": "http://x"})
