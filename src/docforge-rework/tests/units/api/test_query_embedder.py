"""QueryEmbedder — the query-embedding seam, exercised with FAKE embed nodes (no HTTP). Covers the
two provider shapes it must handle: dense-only (the openai-compatible graceful sparse degrade) and
dense+sparse (the pipeline SparseVector → store SparseVec adaptation), plus the config sparse gate."""

import pytest

import shared_libs.pipelines.nodes.embed  # noqa: F401 — ensures the "embed" family exists
from shared_libs.pipelines.build import ActionNodeBlob
from shared_libs.pipelines.nodes.embed.base import BaseEmbedConfig, BaseEmbedderNode
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import SparseVector
from shared_libs.services.db.qdrant import SparseVec


class _FakeDenseOnlyNode(BaseEmbedderNode):
    """A provider with no sparse axis — base `_embed_sparse` returns None (openai-compatible-like)."""

    KIND = "fake_dense_only"
    NAME = "Fake dense-only"
    SUMMARY = "Test embedder without a sparse axis."
    Config = BaseEmbedConfig

    async def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        return [[0.11, 0.22, 0.33] for _ in texts]


class _FakeHybridNode(BaseEmbedderNode):
    """A provider with both axes — dense + sparse (bge_server-like)."""

    KIND = "fake_hybrid"
    NAME = "Fake hybrid"
    SUMMARY = "Test embedder with a sparse axis."
    Config = BaseEmbedConfig

    async def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        return [[0.5, 0.6] for _ in texts]

    async def _embed_sparse(self, texts: list[str]) -> list[SparseVector]:
        return [SparseVector(indices=[3, 9], values=[0.7, 0.8]) for _ in texts]


class _FakeColbertNode(BaseEmbedderNode):
    """A provider that also emits ColBERT multi-vectors (bge_server with embed_colbert on)."""

    KIND = "fake_colbert"
    NAME = "Fake colbert"
    SUMMARY = "Test embedder with a ColBERT axis."
    Config = BaseEmbedConfig

    async def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        return [[0.5, 0.6] for _ in texts]

    def _wants_colbert(self) -> bool:
        return True

    async def _embed_colbert(self, texts: list[str]) -> list[list[list[float]]]:
        # One token-vector matrix per input — here a fixed 2-token x 2-dim matrix.
        return [[[0.1, 0.2], [0.3, 0.4]] for _ in texts]


@pytest.fixture
def registered_fakes():
    """Register the fake embedders under the 'embed' family, then remove them (global registry)."""
    embed = NodeRegistry._store.setdefault("embed", {})
    embed["fake_dense_only"] = _FakeDenseOnlyNode
    embed["fake_hybrid"] = _FakeHybridNode
    embed["fake_colbert"] = _FakeColbertNode
    yield
    embed.pop("fake_dense_only", None)
    embed.pop("fake_hybrid", None)
    embed.pop("fake_colbert", None)


def _blob(kind: str, **config) -> ActionNodeBlob:
    return ActionNodeBlob(id="q", family="embed", kind=kind, config={"model": "fake", **config})


async def test_dense_only_provider_degrades_sparse_to_none(fastapi_app, registered_fakes) -> None:
    """A provider without a sparse axis embeds dense and returns sparse None (no crash)."""
    from backend.routers.search.embedder import QueryEmbedder

    dense, sparse = await QueryEmbedder(_blob("fake_dense_only")).embed("hello")
    assert dense == [0.11, 0.22, 0.33]
    assert sparse is None


async def test_hybrid_provider_adapts_sparse_vector(fastapi_app, registered_fakes) -> None:
    """A dense+sparse provider adapts SparseVector → SparseVec(indices=…, values=…)."""
    from backend.routers.search.embedder import QueryEmbedder

    dense, sparse = await QueryEmbedder(_blob("fake_hybrid")).embed("hello")
    assert dense == [0.5, 0.6]
    assert isinstance(sparse, SparseVec)
    assert sparse.indices == [3, 9]
    assert sparse.values == [0.7, 0.8]


async def test_sparse_gate_off_skips_sparse(fastapi_app, registered_fakes) -> None:
    """embed_sparse=False skips the sparse axis even on a provider that supports it."""
    from backend.routers.search.embedder import QueryEmbedder

    _, sparse = await QueryEmbedder(_blob("fake_hybrid", embed_sparse=False)).embed("hello")
    assert sparse is None


async def test_colbert_provider_exposes_wants_and_embeds_the_query_matrix(
    fastapi_app, registered_fakes
) -> None:
    """A ColBERT provider reports wants_colbert True and returns the query's token matrix."""
    from backend.routers.search.embedder import QueryEmbedder

    embedder = QueryEmbedder(_blob("fake_colbert"))
    assert embedder.wants_colbert() is True
    matrix = await embedder.embed_colbert("hello")
    assert matrix == [[0.1, 0.2], [0.3, 0.4]]  # the [0] of the one-element batch


async def test_non_colbert_provider_reports_wants_false(fastapi_app, registered_fakes) -> None:
    """A provider without ColBERT reports wants_colbert False (the graceful-guard signal)."""
    from backend.routers.search.embedder import QueryEmbedder

    assert QueryEmbedder(_blob("fake_hybrid")).wants_colbert() is False
