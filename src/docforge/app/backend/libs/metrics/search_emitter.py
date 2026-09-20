# ====== Code Summary ======
# SearchMetricsEmitter — the ONLY component that writes SearchMetrics. It is a static, pure function
# of what the runner already holds after a run: the execution record tree (per-node duration/kind/
# score survive TraceLevel.OFF, so nothing extra is captured), the delivered SearchResult, the
# per-request SearchRetrievalProbe, and the family map of the built graph. It lives app-side at the
# runner boundary — a node never emits, and this file is imported DIRECTLY by the runner (not via the
# metrics package __init__) so the search import graph never drags in MetricsService/QueueClient.
#
# The `stage` label is the node's registry FAMILY, resolved from the BUILT graph (family_map walks
# the SAME taxonomy the runner binds on: Group → recurse, ForEach → recurse into .body, ActionNode →
# NodeRegistry.family_of). node_id is used only as a map key, never as a label (a stored blob names
# its nodes arbitrarily — a node_id label would be a user-controlled cardinality leak). Everything is
# best-effort by construction: the runner calls emit() inside its finally, wrapped so this can never
# fail a search.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, ForEach, Group, NodeExecutionRecord
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models.search import SearchResult

# ====== Local Project Imports ======
from ..search.probe import SearchRetrievalProbe
from .search_collectors import SearchMetrics

# The bounded sentinel for a node whose family cannot be resolved — mirrors the HTTP middleware's
# _UNMATCHED discipline so an unexpected node never mints an unbounded label.
_UNKNOWN_FAMILY = "unknown"

# The registry family whose presence means "a rerank pass ran on this search".
_RERANK_FAMILY = "rerank"


class SearchMetricsEmitter:
    """Static emitter that reads a completed search run and feeds the docforge_search_* series."""

    logger = loggerplusplus.bind(identifier="SearchMetricsEmitter")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SearchMetricsEmitter is a static-only class and cannot be instantiated.")

    @classmethod
    def family_map(cls, group: Group) -> dict[str, str]:
        """
        Map every action node's id to its registry family, walking the built graph.

        Walks the SAME node taxonomy the runner binds on (leaves, nested groups AND ForEach bodies)
        so a port-backed node inside a ForEach is labelled by its real family, not "unknown".

        Args:
            group (Group): The built search graph.

        Returns:
            dict[str, str]: node_id → family for every action node reachable in the graph.
        """
        # 1. Depth-first over the same containers the runner descends into.
        mapping: dict[str, str] = {}
        for child in group.children:
            if isinstance(child, Group):
                mapping.update(cls.family_map(child))
            elif isinstance(child, ForEach):
                mapping.update(cls.family_map(child.body))
            elif isinstance(child, ActionNode):
                mapping[child.id] = NodeRegistry.family_of(type(child)) or _UNKNOWN_FAMILY
        return mapping

    @classmethod
    def emit(
        cls,
        *,
        record: NodeExecutionRecord | None,
        result: SearchResult | None,
        probe: SearchRetrievalProbe | None,
        families: dict[str, str],
        outcome: str,
    ) -> None:
        """
        Emit every per-search series for one completed run (success or failure).

        Args:
            record (NodeExecutionRecord | None): The run's root record (None if execute never ran).
            result (SearchResult | None): The delivered result (None on any failure path).
            probe (SearchRetrievalProbe | None): The per-request retrieval probe (None if the port
                exposes none).
            families (dict[str, str]): node_id → family for the built graph.
            outcome (str): The run outcome (success / failed / timeout / unavailable).
        """
        # 1. Run outcome + whole-run latency (both survive every failure path).
        SearchMetrics.RUNS_TOTAL.labels(outcome=outcome).inc()
        if record is not None:
            SearchMetrics.RUN_DURATION_SECONDS.observe(record.duration_ms / 1000.0)
            cls.__observe_stage_latencies(record, families)

        # 2. Success-only shape counters.
        if outcome == "success" and isinstance(result, SearchResult):
            cls.__observe_outcome(result)

        # 3. Retrieval-shape counters from the probe (independent of run outcome).
        if probe is not None:
            cls.__observe_probe(probe)
            cls.__observe_branches(probe)

        # 4. Rerank effect — only when a rerank-family node actually ran.
        if record is not None and isinstance(result, SearchResult):
            cls.__observe_rerank(record, result, probe, families)

    @classmethod
    def __observe_stage_latencies(
        cls, record: NodeExecutionRecord, families: dict[str, str]
    ) -> None:
        """Observe each LEAF record's duration under its family label (groups are skipped)."""
        # 1. A record with no children is a leaf (an action node); a group's duration is a sum and
        #    would double-count, so only leaves feed the per-stage histogram.
        if not record.children:
            stage = families.get(record.node_id, _UNKNOWN_FAMILY)
            SearchMetrics.DURATION_SECONDS.labels(stage=stage).observe(record.duration_ms / 1000.0)
            return
        # 2. Recurse into groups / ForEach item records.
        for child in record.children:
            cls.__observe_stage_latencies(child, families)

    @classmethod
    def __observe_outcome(cls, result: SearchResult) -> None:
        """Observe hit count + the zero-result / degraded counters for a successful run."""
        # 1. Hit count, then the two outcome flags read off the delivered result.
        hit_count = len(result.hits)
        SearchMetrics.HITS.observe(hit_count)
        if hit_count == 0:
            SearchMetrics.ZERO_RESULT_TOTAL.inc()
        if result.debug and result.debug.get("degraded"):
            SearchMetrics.DEGRADED_TOTAL.inc()

    @classmethod
    def __observe_probe(cls, probe: SearchRetrievalProbe) -> None:
        """Observe candidate count + the per-call axes/filter retrieval counter from the probe."""
        # 1. Summed candidate depth over every retrieval call this request made.
        SearchMetrics.CANDIDATES.observe(probe.candidates_total)
        # 2. One retrieval-total increment per call, keyed by its bounded axes + filter flag.
        for axes, filtered in zip(probe.axes, probe.filtered):
            SearchMetrics.RETRIEVAL_TOTAL.labels(axes=axes, filtered=str(filtered).lower()).inc()

    @classmethod
    def __observe_rerank(
        cls,
        record: NodeExecutionRecord,
        result: SearchResult,
        probe: SearchRetrievalProbe | None,
        families: dict[str, str],
    ) -> None:
        """Count a rerank pass and observe how far it moved the delivered hits (displacement)."""
        # 1. Did any leaf resolve to the rerank family?
        if not cls.__rerank_ran(record, families):
            return
        SearchMetrics.RERANK_APPLIED_TOTAL.inc()
        # 2. Displacement is only meaningful against a recorded retrieval order.
        if probe is None:
            return
        shift = cls._rank_shift([hit.chunk_id for hit in result.hits], probe.retrieval_order)
        if shift is not None:
            SearchMetrics.RERANK_RANK_SHIFT.observe(shift)

    @classmethod
    def __rerank_ran(cls, record: NodeExecutionRecord, families: dict[str, str]) -> bool:
        """True when any leaf record maps to the rerank family."""
        # 1. Leaf → check its family; else recurse.
        if not record.children:
            return families.get(record.node_id) == _RERANK_FAMILY
        return any(cls.__rerank_ran(child, families) for child in record.children)

    @classmethod
    def __observe_branches(cls, probe: SearchRetrievalProbe) -> None:
        """Emit the opt-in dense/sparse breakdown ratios + the probe-outcome counter (slice 1B)."""
        # 1. Surface the probe's own cost/health first (an always-failing probe is never silent).
        if probe.branch_probe_ok:
            SearchMetrics.BRANCH_PROBE_TOTAL.labels(outcome="ok").inc(probe.branch_probe_ok)
        if probe.branch_probe_error:
            SearchMetrics.BRANCH_PROBE_TOTAL.labels(outcome="error").inc(probe.branch_probe_error)
        # 2. Ratios need both id sets and a non-empty fused pool (else a degenerate no-op).
        if probe.dense_ids is None or probe.sparse_ids is None:
            return
        fused = set(probe.retrieval_order)
        if not fused:
            return
        cls.__observe_ratios(fused, probe.dense_ids, probe.sparse_ids)

    @classmethod
    def __observe_ratios(cls, fused: set[str], dense_ids: set[str], sparse_ids: set[str]) -> None:
        """Observe the both / dense-only / sparse-only share of the fused pool."""
        # 1. Partition the fused pool by branch membership and observe each share.
        total = len(fused)
        both = len(fused & dense_ids & sparse_ids)
        dense_only = len(fused & (dense_ids - sparse_ids))
        sparse_only = len(fused & (sparse_ids - dense_ids))
        SearchMetrics.BRANCH_CONTRIBUTION_RATIO.labels(branch="both").observe(both / total)
        SearchMetrics.BRANCH_CONTRIBUTION_RATIO.labels(branch="dense_only").observe(
            dense_only / total
        )
        SearchMetrics.BRANCH_CONTRIBUTION_RATIO.labels(branch="sparse_only").observe(
            sparse_only / total
        )

    @classmethod
    def _rank_shift(cls, delivered_ids: list[str], retrieval_order: list[str]) -> float | None:
        """
        Mean absolute rank displacement of the delivered hits vs their retrieval rank.

        Scale-free (unlike a raw pre/post score delta across incomparable scales), it answers "did
        rerank actually move anything?".

        Args:
            delivered_ids (list[str]): Chunk ids in delivered (post-rerank) order.
            retrieval_order (list[str]): Chunk ids in retrieval (pre-rerank) order.

        Returns:
            float | None: The mean absolute displacement, or None when there is nothing to compare.
        """
        # 1. Nothing to compare — empty hits or no recorded order.
        if not delivered_ids or not retrieval_order:
            return None
        # 2. First-occurrence retrieval rank per id.
        retrieval_rank = {}
        for rank, chunk_id in enumerate(retrieval_order):
            retrieval_rank.setdefault(chunk_id, rank)
        # 3. Sum absolute displacement over the delivered hits that were in the retrieval pool.
        shifts = [
            abs(delivered_rank - retrieval_rank[chunk_id])
            for delivered_rank, chunk_id in enumerate(delivered_ids)
            if chunk_id in retrieval_rank
        ]
        if not shifts:
            return None
        return sum(shifts) / len(shifts)


__all__ = ["SearchMetricsEmitter"]
