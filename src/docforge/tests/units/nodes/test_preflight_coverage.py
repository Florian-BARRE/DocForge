"""Preflight coverage for the three network-calling nodes that previously escaped the sweep.

Before the 0.14.0 fix, ``FigureClassifyNode`` (hosted VLM), ``ChunkerSemanticNode`` (embeddings) and
the metagen PREP nodes (default LLM endpoint) defined no ``preflight()``, so the worker reachability
sweep (``probes_endpoint`` = "does it override ``ActionNode.preflight``?") marked them SKIPPED and a
wrong/unreachable endpoint only failed MID-RUN, after paid parse/render (invariant #4). These tests
prove each one now:
  * reports ``probes_endpoint`` True (the sweep picks it up);
  * probes its configured endpoint (reachable -> passes, unreachable -> PreflightError);
and that a fully-local ``figure_classify`` (classify_backend="local") stays a no-op (no network call),
and a metagen prep whose default endpoint is empty (all per-target overrides) is skipped.
httpx is mocked — no network.
"""

import httpx
import pytest

from shared_libs.pipelines.ingest.nodes.chunk.semantic import (
    ChunkerSemanticConfig,
    ChunkerSemanticNode,
)
from shared_libs.pipelines.ingest.nodes.enrich.figure_classify import (
    FigureClassifyConfig,
    FigureClassifyNode,
)
from shared_libs.pipelines.ingest.nodes.metagen.prep import (
    MetagenChunkPrepConfig,
    MetagenChunkPrepNode,
    MetagenDocumentPrepConfig,
    MetagenDocumentPrepNode,
)
from shared_libs.pipelines.nodes.embed.openai_compatible import (
    EmbedOpenAICompatibleConfig,
    EmbedOpenAICompatibleNode,
)
from shared_libs.pipelines.nodes.openai_compat.preflight import (
    EndpointIncompatibleError,
    PreflightError,
)
from shared_libs.pipelines.reachability import ReachabilitySweep


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def _fake_client(*, status_code: int | None = None, raises: Exception | None = None):
    """A stand-in for httpx.AsyncClient: an async context manager whose .get() answers or raises."""

    class _Client:
        def __init__(self, *args: object, **kwargs: object) -> None: ...

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *exc: object) -> None: ...

        async def get(self, url: str, headers: dict | None = None) -> _FakeResponse:
            if raises is not None:
                raise raises
            return _FakeResponse(status_code)

    return _Client


def _exploding_client(*args: object, **kwargs: object):
    """A client whose mere use is a test failure — proves preflight made NO network call."""
    raise AssertionError("preflight must not touch the network for a local/empty-endpoint node")


# ---------------------- FigureClassifyNode (hosted VLM) ---------------------- #


def _vlm_classify() -> FigureClassifyNode:
    return FigureClassifyNode(
        id="classify", config=FigureClassifyConfig(base_url="http://vlm:8000", model="qwen")
    )


def _local_classify() -> FigureClassifyNode:
    # A deliberately bogus endpoint: if the local backend probed it, the exploding client would fire.
    return FigureClassifyNode(
        id="classify",
        config=FigureClassifyConfig(classify_backend="local", base_url="http://nope:9"),
    )


def test_vlm_figure_classify_is_picked_up_by_the_sweep() -> None:
    assert ReachabilitySweep.probes_endpoint(_vlm_classify()) is True


async def test_vlm_figure_classify_probes_its_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(status_code=200))
    await _vlm_classify().preflight()  # reachable -> no raise


async def test_vlm_figure_classify_unreachable_fails(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(raises=httpx.ConnectError("refused")))
    with pytest.raises(PreflightError, match="unreachable"):
        await _vlm_classify().preflight()


async def test_local_figure_classify_is_a_noop(monkeypatch) -> None:
    # The local backend has no endpoint: preflight must return None WITHOUT any network call.
    monkeypatch.setattr(httpx, "AsyncClient", _exploding_client)
    assert await _local_classify().preflight() is None


# ---------------------- ChunkerSemanticNode (embeddings) ---------------------- #


def _semantic() -> ChunkerSemanticNode:
    return ChunkerSemanticNode(
        id="chunk", config=ChunkerSemanticConfig(base_url="http://bge:80", model="bge-m3")
    )


def test_semantic_chunker_is_picked_up_by_the_sweep() -> None:
    assert ReachabilitySweep.probes_endpoint(_semantic()) is True


async def test_semantic_chunker_probes_its_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(status_code=200))
    await _semantic().preflight()  # reachable -> no raise


async def test_semantic_chunker_unreachable_fails(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(raises=httpx.ConnectError("refused")))
    with pytest.raises(PreflightError, match="unreachable"):
        await _semantic().preflight()


async def test_semantic_chunker_missing_embeddings_route_fails_with_actionable_message(
    monkeypatch,
) -> None:
    # A TEI-only server (bge_server) answers on the host but has no /embeddings route -> 404. The
    # capability probe must turn that into an actionable fail-fast, NOT let it slip to a mid-run 404.
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(status_code=404))
    with pytest.raises(EndpointIncompatibleError, match="not found") as exc_info:
        await _semantic().preflight()
    message = str(exc_info.value)
    assert "/embeddings" in message
    assert "TEI" in message  # names the likely culprit, so the fix is obvious


async def test_semantic_chunker_present_embeddings_route_passes(monkeypatch) -> None:
    # A real OpenAI-compatible server answers 405 to a GET on its POST-only /embeddings route: the
    # route EXISTS, so preflight passes (only a 404 means the route is absent).
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(status_code=405))
    await _semantic().preflight()


# ---------------------- EmbedOpenAICompatibleNode (/v1/embeddings) ---------------------- #


def _embed_openai() -> EmbedOpenAICompatibleNode:
    return EmbedOpenAICompatibleNode(
        id="embed", config=EmbedOpenAICompatibleConfig(base_url="http://bge:80", model="bge-m3")
    )


async def test_embed_openai_missing_embeddings_route_fails_with_actionable_message(
    monkeypatch,
) -> None:
    # Same trap as the semantic chunker: a TEI-only server answers on the host but has no
    # /embeddings route -> 404. The capability probe must fail fast with an actionable message.
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(status_code=404))
    with pytest.raises(EndpointIncompatibleError, match="not found") as exc_info:
        await _embed_openai().preflight()
    message = str(exc_info.value)
    assert "/embeddings" in message
    assert "TEI" in message


async def test_embed_openai_present_embeddings_route_passes(monkeypatch) -> None:
    # A real OpenAI-compatible server answers 405 to a GET on its POST-only /embeddings route.
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(status_code=405))
    await _embed_openai().preflight()


async def test_embed_openai_unreachable_fails(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(raises=httpx.ConnectError("refused")))
    with pytest.raises(PreflightError, match="unreachable"):
        await _embed_openai().preflight()


# ---------------------- Metagen prep (default LLM endpoint) ---------------------- #


def _chunk_prep(base_url: str = "http://llm:8000") -> MetagenChunkPrepNode:
    return MetagenChunkPrepNode(
        id="meta_chunk_prep", config=MetagenChunkPrepConfig(base_url=base_url, model="gpt")
    )


def _document_prep(base_url: str = "http://llm:8000") -> MetagenDocumentPrepNode:
    return MetagenDocumentPrepNode(
        id="meta_doc_prep", config=MetagenDocumentPrepConfig(base_url=base_url, model="gpt")
    )


def test_metagen_prep_nodes_are_picked_up_by_the_sweep() -> None:
    assert ReachabilitySweep.probes_endpoint(_chunk_prep()) is True
    assert ReachabilitySweep.probes_endpoint(_document_prep()) is True


async def test_metagen_prep_probes_its_default_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(status_code=200))
    await _chunk_prep().preflight()  # reachable -> no raise
    await _document_prep().preflight()


async def test_metagen_prep_unreachable_default_endpoint_fails(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(raises=httpx.ConnectError("refused")))
    with pytest.raises(PreflightError, match="unreachable"):
        await _chunk_prep().preflight()


async def test_metagen_prep_with_empty_default_endpoint_is_a_noop(monkeypatch) -> None:
    # A config whose default endpoint is empty (every field bound to its own per-target override)
    # has nothing to probe here — no network call, no raise (mirrors the structgen head's guard).
    monkeypatch.setattr(httpx, "AsyncClient", _exploding_client)
    assert await _chunk_prep(base_url="").preflight() is None
