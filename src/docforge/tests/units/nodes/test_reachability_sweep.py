"""ReachabilitySweep — the public seam behind the worker preflight and the collection-health probe.

Covers the honest projection of each provider leaf's preflight() onto a ProviderProbeResult
(provider answered → ok, transport error → unreachable, 401/403 → auth_failed, local leaf → skipped),
that the walk recurses groups + ForEach bodies, and the SearchReachabilitySweep composing the query
embedder (from the pipeline blob) + the reranker (from the search graph). httpx is mocked — no
network. The worker's delegation to this seam is covered in tests/units/worker/test_worker_runner.py.
"""

import httpx

from shared_libs.pipelines.base import ForEach, FromRunInput, Group
from shared_libs.pipelines.ingest.nodes.enrich.figure_entry import (
    FigureEntryConfig,
    FigureEntryNode,
)
from shared_libs.pipelines.nodes.embed.bge_server import (
    EmbedBgeServerConfig,
    EmbedBgeServerNode,
)
from shared_libs.pipelines.reachability import (
    ProbeStatus,
    ReachabilitySweep,
    SearchReachabilitySweep,
)
from shared_libs.pipelines.search.nodes.rerank.cross_encoder.config import (
    RerankCrossEncoderConfig,
)
from shared_libs.pipelines.search.nodes.rerank.cross_encoder.core import (
    RerankCrossEncoderNode,
)


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


def _provider() -> EmbedBgeServerNode:
    """A provider leaf that overrides preflight() (probes an endpoint)."""
    return EmbedBgeServerNode(id="embed", config=EmbedBgeServerConfig(base_url="http://bge:80"))


def _local() -> FigureEntryNode:
    """A local leaf with no preflight override (nothing to reach)."""
    return FigureEntryNode(id="entry", config=FigureEntryConfig())


def test_probes_endpoint_distinguishes_provider_from_local() -> None:
    assert ReachabilitySweep.probes_endpoint(_provider()) is True
    assert ReachabilitySweep.probes_endpoint(_local()) is False


async def test_reachable_provider_is_ok(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(status_code=200))
    [result] = await ReachabilitySweep().probe_nodes([_provider()], "ingest")
    assert result.status is ProbeStatus.OK
    assert result.side == "ingest"
    assert result.family == "embed"
    assert result.detail is None
    assert result.latency_ms is not None


async def test_rejected_credentials_is_auth_failed(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(status_code=401))
    [result] = await ReachabilitySweep().probe_nodes([_provider()], "ingest")
    assert result.status is ProbeStatus.AUTH_FAILED
    assert result.detail


async def test_transport_error_is_unreachable(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(raises=httpx.ConnectError("refused")))
    [result] = await ReachabilitySweep().probe_nodes([_provider()], "search")
    assert result.status is ProbeStatus.UNREACHABLE
    assert result.side == "search"


async def test_local_leaf_is_skipped() -> None:
    [result] = await ReachabilitySweep().probe_nodes([_local()], "ingest")
    assert result.status is ProbeStatus.SKIPPED
    assert result.latency_ms is None


def test_collect_leaves_recurses_groups_and_foreach() -> None:
    # A provider at the top level + a local leaf nested inside a ForEach body group.
    body = Group(id="body", children=[_local()])
    loop = ForEach(id="loop", body=body, over=FromRunInput(field_name="items"), item_field="item")
    graph = Group(id="root", children=[_provider(), loop])
    leaves = ReachabilitySweep.collect_leaves(graph)
    assert {leaf.id for leaf in leaves} == {"embed", "entry"}


def _pipeline_blob_with_embedder() -> dict:
    """A minimal ingest blob carrying one bge_server embed node."""
    return {
        "nodes": [
            {
                "family": "embed",
                "kind": "bge_server",
                "id": "embed",
                "config": {"base_url": "http://bge:80"},
            }
        ]
    }


async def test_search_sweep_probes_embedder_and_reranker(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(status_code=200))
    # A search graph with the reranker (provider) + a local leaf that must be excluded.
    rerank = RerankCrossEncoderNode(id="rerank", config=RerankCrossEncoderConfig())
    search_graph = Group(id="search", children=[rerank, _local()])
    results = await SearchReachabilitySweep().sweep(_pipeline_blob_with_embedder(), search_graph)
    # The query embedder (from the pipeline blob) + the reranker — the local leaf is left out.
    assert {(r.family, r.node_id) for r in results} == {("embed", "embed"), ("rerank", "rerank")}
    assert all(r.side == "search" and r.status is ProbeStatus.OK for r in results)


async def test_search_sweep_without_embedder_returns_only_providers() -> None:
    # No embed node in the pipeline blob → no embedder result; an empty search graph carries no
    # reranker either, so the sweep still appends the synthetic not_configured rerank entry (it is
    # ALWAYS reported, present or absent, so the client never has to infer absence from omission).
    results = await SearchReachabilitySweep().sweep({"nodes": []}, Group(id="search", children=[]))
    assert len(results) == 1
    [rerank_result] = results
    assert rerank_result.family == "rerank"
    assert rerank_result.status is ProbeStatus.NOT_CONFIGURED
