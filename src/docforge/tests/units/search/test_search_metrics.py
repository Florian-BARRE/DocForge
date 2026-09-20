"""Per-search telemetry (slice 1A): the SearchMetricsEmitter is a pure function of a built graph's
family map + a hand-built execution record tree + the delivered result + the retrieval probe. No
engine run is needed — these assert the SERIES and LABELS the emitter feeds, the family `stage`
label (never a node_id), the outcome/shape counters, the rerank rank-displacement, and the D2
containment invariant (an emitter that raises never fails the search)."""

import asyncio

import pytest
from prometheus_client import REGISTRY

from backend.libs.metrics.search_emitter import SearchMetricsEmitter
from backend.libs.search.probe import (
    AXES_DENSE_ONLY,
    SearchRetrievalProbe,
)
from shared_libs.pipelines.base import (
    ForEach,
    Group,
    NodeExecutionRecord,
    NodeStatus,
)
from shared_libs.pipelines.base.io import FromRunInput
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.nodes.embed.base import BaseEmbedConfig, BaseEmbedderNode
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.pipelines.search import CollectionReadPort, SearchPipeline
from shared_libs.pipelines.search.nodes.retrieve.hybrid.core import (
    RetrieveHybridConfig,
    RetrieveHybridNode,
)
from shared_libs.public_models.search import (
    Candidate,
    Hit,
    QueryFilters,
    RawQuery,
    SearchContract,
    SearchResult,
)


# ---------------------- Test doubles (uniquely named — the registry is process-global) ---------- #
class _MetricsEmbedConfig(BaseEmbedConfig):
    """Config of this module's HTTP-free test embedder."""


@NodeRegistry.register("embed")
class FakeMetricsEmbedNode(BaseEmbedderNode):
    """A deterministic, HTTP-free embedder — a distinct KIND so it never collides with other tests."""

    KIND = "fake_metrics_embed"
    NAME = "Fake metrics embedder"
    SUMMARY = "Deterministic embedder for the metrics tests (no HTTP)."
    Config = _MetricsEmbedConfig

    async def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        """A fixed 4-d dense vector per text — no network."""
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]


class _MetricsMockPort(CollectionReadPort):
    """A read port returning 2 fake candidates and hydrating them — no store, no probe."""

    async def hybrid_search(
        self, encoded, filters, limit, targets=None, fusion="rrf", measure_branch_contribution=False
    ):
        return [
            Candidate(chunk_id="c1", score=0.9, source="hybrid"),
            Candidate(chunk_id="c2", score=0.7, source="hybrid"),
        ]

    async def hydrate(self, chunk_ids):
        return {
            cid: Hit(chunk_id=cid, document_id=f"d-{cid}", text=cid, metadata={})
            for cid in chunk_ids
        }


def _metrics_run_input() -> dict:
    """A minimal search run-input driven by this module's fake embedder."""
    return {
        "query": RawQuery(text="hello", top_k=2, flags={}),
        "filters": QueryFilters(filters={}),
        "contract": SearchContract(
            collection_id="col-1",
            embed_kind="fake_metrics_embed",
            embed_config={"model": "fake", "embed_sparse": False},
        ),
    }


# ---------------------- Helpers ---------------------- #
def _val(name: str, labels: dict | None = None) -> float:
    """Current registry sample value for a series (0.0 when never observed) — for delta asserts."""
    value = REGISTRY.get_sample_value(name, labels or {})
    return value if value is not None else 0.0


def _leaf(node_id: str, duration_ms: float = 10.0) -> NodeExecutionRecord:
    """A leaf (childless) execution record."""
    return NodeExecutionRecord(
        node_id=node_id, kind="x", status=NodeStatus.SUCCESS, duration_ms=duration_ms
    )


def _root(children: list[NodeExecutionRecord], duration_ms: float = 100.0) -> NodeExecutionRecord:
    """A root group record wrapping leaves (its own duration feeds the run-duration histogram)."""
    return NodeExecutionRecord(
        node_id="search",
        kind="group",
        status=NodeStatus.SUCCESS,
        duration_ms=duration_ms,
        children=children,
    )


def _result(hits: list[str], degraded: str | None = None) -> SearchResult:
    """A SearchResult with the given hit chunk ids (rank order) and optional degraded note."""
    debug = {"hit_count": len(hits)}
    if degraded:
        debug["degraded"] = degraded
    return SearchResult(
        query="q",
        hits=[Hit(chunk_id=cid, document_id="d", rank=i + 1) for i, cid in enumerate(hits)],
        debug=debug,
    )


# ---------------------- family_map (D4 taxonomy parity) ---------------------- #
def test_family_map_covers_leaves_of_the_real_stock_graph() -> None:
    """The stock search graph's nodes each map to their registry family (never a kind)."""
    group = PipelineBuilder().build(SearchPipeline.default_blob())
    families = SearchMetricsEmitter.family_map(group)
    assert families["retrieve"] == "retrieve"
    assert families["encode"] == "encode"
    assert families["deliver"] == "deliver"


def test_family_map_recurses_into_foreach_bodies() -> None:
    """A port-backed node inside a ForEach body is labelled by its real family, not skipped."""
    node = RetrieveHybridNode("inner_retrieve", RetrieveHybridConfig())
    body = Group("body", children=[node])
    foreach = ForEach("loop", body=body, over=FromRunInput(field_name="query"), item_field="item")
    root = Group("root", children=[foreach])

    families = SearchMetricsEmitter.family_map(root)
    assert families == {"inner_retrieve": "retrieve"}


# ---------------------- stage latency + cardinality (D4) ---------------------- #
def test_leaf_durations_observed_under_family_label_groups_skipped() -> None:
    """Each LEAF duration is observed once under its family; the group's duration is NOT."""
    before_stage = _val("docforge_search_duration_seconds_count", {"stage": "retrieve"})
    before_run = _val("docforge_search_run_duration_seconds_count")

    record = _root([_leaf("retrieve", 20.0), _leaf("deliver", 5.0)])
    families = {"retrieve": "retrieve", "deliver": "deliver"}
    SearchMetricsEmitter.emit(
        record=record, result=_result(["c1"]), probe=None, families=families, outcome="success"
    )

    assert _val("docforge_search_duration_seconds_count", {"stage": "retrieve"}) == before_stage + 1
    # The root group fed run-duration exactly once (its child leaves fed per-stage instead).
    assert _val("docforge_search_run_duration_seconds_count") == before_run + 1


def test_unmapped_node_id_falls_back_to_unknown_and_no_node_id_label() -> None:
    """A leaf absent from the family map is labelled 'unknown'; no series carries a node_id label."""
    before = _val("docforge_search_duration_seconds_count", {"stage": "unknown"})
    SearchMetricsEmitter.emit(
        record=_root([_leaf("mystery_node", 7.0)]),
        result=_result(["c1"]),
        probe=None,
        families={},
        outcome="success",
    )
    assert _val("docforge_search_duration_seconds_count", {"stage": "unknown"}) == before + 1

    # No docforge_search_* series may carry a node_id or collection_id label (cardinality leak repro).
    for metric in REGISTRY.collect():
        if not metric.name.startswith("docforge_search"):
            continue
        for sample in metric.samples:
            assert "node_id" not in sample.labels
            assert "collection_id" not in sample.labels


# ---------------------- outcome + shape counters ---------------------- #
def test_zero_result_and_degraded_counters_fire_off_the_result() -> None:
    """zero_result increments on empty hits; degraded increments on a degraded debug note."""
    before_zero = _val("docforge_search_zero_result_total")
    before_degraded = _val("docforge_search_degraded_total")

    SearchMetricsEmitter.emit(
        record=_root([_leaf("retrieve")]),
        result=_result([], degraded="dense axis unavailable"),
        probe=None,
        families={"retrieve": "retrieve"},
        outcome="success",
    )
    assert _val("docforge_search_zero_result_total") == before_zero + 1
    assert _val("docforge_search_degraded_total") == before_degraded + 1


def test_runs_total_labels_the_outcome_on_a_failure_path() -> None:
    """A timeout run still increments runs_total{outcome=timeout} (failures emit too)."""
    before = _val("docforge_search_runs_total", {"outcome": "timeout"})
    SearchMetricsEmitter.emit(record=None, result=None, probe=None, families={}, outcome="timeout")
    assert _val("docforge_search_runs_total", {"outcome": "timeout"}) == before + 1


def test_probe_feeds_candidates_and_the_axes_filter_counter() -> None:
    """The probe drives candidate count + a retrieval_total increment per call (axes × filtered)."""
    before = _val("docforge_search_retrieval_total", {"axes": AXES_DENSE_ONLY, "filtered": "true"})
    probe = SearchRetrievalProbe()
    probe.record_call(AXES_DENSE_ONLY, True, ["c1", "c2"])
    SearchMetricsEmitter.emit(
        record=_root([_leaf("retrieve")]),
        result=_result(["c1"]),
        probe=probe,
        families={"retrieve": "retrieve"},
        outcome="success",
    )
    assert (
        _val("docforge_search_retrieval_total", {"axes": AXES_DENSE_ONLY, "filtered": "true"})
        == before + 1
    )


# ---------------------- rerank rank-displacement (D8) ---------------------- #
def test_rerank_applied_only_when_a_rerank_family_ran() -> None:
    """rerank_applied fires only when a rerank-family leaf executed; not on a plain hybrid run."""
    before = _val("docforge_search_rerank_applied_total")
    SearchMetricsEmitter.emit(
        record=_root([_leaf("retrieve")]),
        result=_result(["c1"]),
        probe=None,
        families={"retrieve": "retrieve"},
        outcome="success",
    )
    assert _val("docforge_search_rerank_applied_total") == before  # no rerank leaf → no increment

    SearchMetricsEmitter.emit(
        record=_root([_leaf("retrieve"), _leaf("rerank")]),
        result=_result(["c1"]),
        probe=SearchRetrievalProbe(),
        families={"retrieve": "retrieve", "rerank": "rerank"},
        outcome="success",
    )
    assert _val("docforge_search_rerank_applied_total") == before + 1


def test_rank_shift_measures_displacement_and_returns_none_when_incomparable() -> None:
    """_rank_shift is the mean abs displacement; None when there is nothing to compare."""
    # Delivered order c3,c1,c2 vs retrieval order c1,c2,c3 → |0-2|,|1-0|,|2-1| = 2,1,1 → mean 4/3.
    assert SearchMetricsEmitter._rank_shift(
        ["c3", "c1", "c2"], ["c1", "c2", "c3"]
    ) == pytest.approx(4 / 3)
    assert SearchMetricsEmitter._rank_shift([], ["c1"]) is None
    assert SearchMetricsEmitter._rank_shift(["c1"], []) is None
    # Identity order → zero displacement (not None).
    assert SearchMetricsEmitter._rank_shift(["c1", "c2"], ["c1", "c2"]) == 0.0


# ---------------------- D2 containment: a raising emitter never fails the search ---------------------- #
def test_emitter_failure_never_fails_the_run(monkeypatch) -> None:
    """With the emitter monkeypatched to raise, SearchRunner.run still returns + releases the graph."""
    from backend.libs.search.runner import SearchRunner
    from shared_libs.pipelines.ingest.estimate import RateTable

    runner = SearchRunner()
    blob = SearchPipeline.default_blob().model_dump(mode="json")
    port = _MetricsMockPort()

    def _boom(**kwargs):
        raise RuntimeError("metrics blew up")

    monkeypatch.setattr(SearchMetricsEmitter, "emit", staticmethod(_boom))

    result, _usage = asyncio.run(
        runner.run(
            blob,
            _metrics_run_input(),
            port,
            RateTable.from_overrides(None),
            graph_key="stock-metrics",
        )
    )
    # The run still delivered its result despite the raising emitter...
    assert isinstance(result, SearchResult)
    # ...and the graph was released back to the pool (its lock is free to re-acquire).
    assert runner._pool.acquire(
        "stock-metrics", lambda: PipelineBuilder().build(SearchPipeline.default_blob())
    )
