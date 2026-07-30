"""QueryEmbedder — the late-interaction CAPABILITY probe, exercised with FAKE embed nodes (no HTTP).
It rebuilds the collection's embedder from the stored blob and reports whether that embedder emits a
ColBERT axis — the single signal the search route uses to decide whether a ColBERT re-score is even
possible. The query encoding itself is the search graph's job, not this seam."""

import pytest

import shared_libs.pipelines.nodes.embed  # noqa: F401 — ensures the "embed" family exists
from shared_libs.pipelines.build import ActionNodeBlob
from shared_libs.pipelines.nodes.embed.base import BaseEmbedConfig, BaseEmbedderNode
from shared_libs.pipelines.registry import NodeRegistry


class _FakeHybridNode(BaseEmbedderNode):
    """A provider with both axes but NO ColBERT (bge_server-like) — wants_colbert is False."""

    KIND = "fake_hybrid"
    NAME = "Fake hybrid"
    SUMMARY = "Test embedder with a sparse axis but no ColBERT."
    Config = BaseEmbedConfig

    async def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        return [[0.5, 0.6] for _ in texts]


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


@pytest.fixture
def registered_fakes():
    """Register the fake embedders under the 'embed' family, then remove them (global registry)."""
    embed = NodeRegistry._store.setdefault("embed", {})
    embed["fake_hybrid"] = _FakeHybridNode
    embed["fake_colbert"] = _FakeColbertNode
    yield
    embed.pop("fake_hybrid", None)
    embed.pop("fake_colbert", None)


def _blob(kind: str, **config) -> ActionNodeBlob:
    return ActionNodeBlob(id="q", family="embed", kind=kind, config={"model": "fake", **config})


async def test_colbert_provider_reports_wants_true(fastapi_app, registered_fakes) -> None:
    """A ColBERT provider reports wants_colbert True (late interaction is possible)."""
    from backend.routers.search.embedder import QueryEmbedder

    assert QueryEmbedder(_blob("fake_colbert")).wants_colbert() is True


async def test_non_colbert_provider_reports_wants_false(fastapi_app, registered_fakes) -> None:
    """A provider without ColBERT reports wants_colbert False (the graceful-guard signal)."""
    from backend.routers.search.embedder import QueryEmbedder

    assert QueryEmbedder(_blob("fake_hybrid")).wants_colbert() is False
