"""ReachabilitySweep over the multi-endpoint ``(embed, dense_sparse)`` leaf — the egress gate covers
EVERY slot endpoint (a sparse slot on a non-allowlisted host cannot ride along an allowed dense one),
an in-process-only leaf (bm25_local sparse, dense off) is skipped, the surfaced endpoint names every
slot endpoint, and the outer probe cap covers the leaf's sequential per-endpoint probes. httpx is
mocked — no network.
"""

import httpx

from shared_libs.pipelines.nodes.embed.dense_sparse import (
    EmbedDenseSparseConfig,
    EmbedDenseSparseNode,
)
from shared_libs.pipelines.nodes.openai_compat import EndpointReachability
from shared_libs.pipelines.reachability import ProbeStatus, ProviderEgressPolicy, ReachabilitySweep

DENSE = {"kind": "openai_compatible", "base_url": "http://dense-host:8000/v1", "model": "m"}
SPARSE_ELSEWHERE = {"kind": "bge_server", "base_url": "http://evil-host:80"}


def _recording_client(calls: list[str], status_code: int = 200):
    """A stand-in for httpx.AsyncClient recording every GET it would send."""

    class _Response:
        def __init__(self) -> None:
            self.status_code = status_code

    class _Client:
        def __init__(self, *args: object, **kwargs: object) -> None: ...

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *exc: object) -> None: ...

        async def get(self, url: str, headers: dict | None = None) -> _Response:
            calls.append(url)
            return _Response()

    return _Client


def _node(dense: dict | None, sparse: dict | None) -> EmbedDenseSparseNode:
    """A dense_sparse leaf with the given slots."""
    return EmbedDenseSparseNode(
        id="embed", config=EmbedDenseSparseConfig(dense=dense, sparse=sparse)
    )


async def test_a_disallowed_sparse_slot_blocks_the_leaf_without_any_probe(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(httpx, "AsyncClient", _recording_client(calls))
    policy = ProviderEgressPolicy.from_spec("dense-host")  # the sparse slot's host is NOT listed

    [result] = await ReachabilitySweep().probe_nodes(
        [_node(DENSE, SPARSE_ELSEWHERE)], "ingest", policy
    )

    assert result.status is ProbeStatus.BLOCKED
    assert "evil-host" in result.detail and "dense-host" not in result.detail
    assert calls == []  # neither endpoint was reached
    assert result.latency_ms is None


async def test_all_slot_endpoints_allowed_are_probed_and_surfaced(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(httpx, "AsyncClient", _recording_client(calls))
    policy = ProviderEgressPolicy.from_spec("dense-host,evil-host")

    [result] = await ReachabilitySweep().probe_nodes(
        [_node(DENSE, SPARSE_ELSEWHERE)], "ingest", policy
    )

    assert result.status is ProbeStatus.OK
    assert "dense-host" in result.endpoint and "evil-host" in result.endpoint
    assert any("dense-host" in url for url in calls) and any("evil-host" in url for url in calls)


async def test_combined_in_stack_pair_passes_a_guard_listing_its_host(monkeypatch) -> None:
    # Pre-fix the leaf had no top-level base_url → a guard-ON sweep refused it whatever the list.
    monkeypatch.setattr(httpx, "AsyncClient", _recording_client([]))
    policy = ProviderEgressPolicy.from_spec("bge_server")
    [result] = await ReachabilitySweep().probe_nodes(
        [EmbedDenseSparseNode(id="embed", config=EmbedDenseSparseConfig())], "ingest", policy
    )
    assert result.status is ProbeStatus.OK
    assert result.endpoint == "http://bge_server:80"


async def test_in_process_only_leaf_is_skipped(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(httpx, "AsyncClient", _recording_client(calls))
    policy = ProviderEgressPolicy.from_spec("nothing-listed")
    [result] = await ReachabilitySweep().probe_nodes(
        [_node(None, {"kind": "bm25_local"})], "ingest", policy
    )
    assert result.status is ProbeStatus.SKIPPED
    assert calls == []


def test_preflight_budget_sums_each_distinct_endpoint() -> None:
    one = EndpointReachability.budget(3)
    combined = _node(
        {"kind": "bge_server", "base_url": "http://b:80", "preflight_timeout_seconds": 3},
        {"kind": "bge_server", "base_url": "http://b:80/", "preflight_timeout_seconds": 3},
    )
    assert combined.preflight_budget_seconds() == one
    split = _node(
        {**DENSE, "preflight_timeout_seconds": 3},
        {**SPARSE_ELSEWHERE, "preflight_timeout_seconds": 3},
    )
    assert split.preflight_budget_seconds() == 2 * one
