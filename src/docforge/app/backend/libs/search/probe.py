# ====== Code Summary ======
# SearchRetrievalProbe — a pure, per-request accumulator of retrieval FACTS that only the app-side
# read port can see (candidate counts, which axes were queried, the retrieval order, and — when the
# opt-in dense/sparse breakdown is on — the per-branch id sets). It imports NO prometheus_client and
# performs NO I/O: the read port fills it as a side effect of the queries it already runs, and the
# SearchMetricsEmitter reads it once at the runner boundary to emit the series. Two responsibilities,
# two classes, one emission point — so the port stays a pure retrieval component and no node ever
# learns a metric exists. One instance per request (constructed alongside the per-request read port),
# so it carries no cross-request state.

# ====== Standard Library Imports ======
from dataclasses import dataclass, field

# The bounded enum of retrieval axes a single hybrid_search call can query — kept in sync with the
# SearchMetrics.RETRIEVAL_TOTAL `axes` label so the label cardinality can never leak.
AXES_DENSE_SPARSE = "dense_sparse"
AXES_DENSE_ONLY = "dense_only"
AXES_SPARSE_ONLY = "sparse_only"
AXES_NONE = "none"

# Cap on the recorded retrieval order — memory stays bounded whatever candidate_k a stored blob asks
# for (the order is used only for the scale-free rerank-displacement measure, a sample suffices).
_RETRIEVAL_ORDER_CAP = 200


@dataclass(slots=True)
class SearchRetrievalProbe:
    """
    Per-request accumulator of retrieval facts the read port sees but a node/emitter cannot.

    Attributes:
        calls (int): Number of hybrid_search calls this request made (>1 under a ForEach over
            sub-queries).
        candidates_total (int): Summed candidate count over all retrieval calls.
        axes (list[str]): One bounded axes value (AXES_*) per call, in call order.
        filtered (list[bool]): Whether each call carried a structured filter, in call order.
        retrieval_order (list[str]): Candidate chunk ids in retrieval order, capped so memory stays
            bounded; used only for the rerank-displacement measure.
        dense_ids (set[str] | None): Chunk ids the dense-only probe returned — None unless the opt-in
            branch breakdown ran (slice 1B).
        sparse_ids (set[str] | None): Chunk ids the sparse-only probe returned — None unless the
            opt-in branch breakdown ran (slice 1B).
        branch_probe_ok (int): How many branch probes completed (visibility for the opt-in cost).
        branch_probe_error (int): How many branch probes failed (so an always-failing probe is never
            silent — it degrades the breakdown, never the search).
    """

    calls: int = 0
    candidates_total: int = 0
    axes: list[str] = field(default_factory=list)
    filtered: list[bool] = field(default_factory=list)
    retrieval_order: list[str] = field(default_factory=list)
    dense_ids: set[str] | None = None
    sparse_ids: set[str] | None = None
    branch_probe_ok: int = 0
    branch_probe_error: int = 0

    def record_call(self, axes: str, filtered: bool, candidate_ids: list[str]) -> None:
        """
        Record one hybrid_search call's shape facts.

        Args:
            axes (str): The bounded axes value (one of the AXES_* constants) the call queried.
            filtered (bool): Whether the call carried a structured filter.
            candidate_ids (list[str]): The candidate chunk ids the call returned, in retrieval order.
        """
        # 1. Accumulate the scalar counters and the per-call bounded-label lists.
        self.calls += 1
        self.candidates_total += len(candidate_ids)
        self.axes.append(axes)
        self.filtered.append(filtered)

        # 2. Extend the retrieval order up to the cap (a sample is enough for displacement).
        room = _RETRIEVAL_ORDER_CAP - len(self.retrieval_order)
        if room > 0:
            self.retrieval_order.extend(candidate_ids[:room])

    def record_branches(self, dense_ids: set[str], sparse_ids: set[str]) -> None:
        """
        Record a successful dense/sparse branch probe (slice 1B), unioning across calls.

        Args:
            dense_ids (set[str]): Chunk ids the dense-only probe returned.
            sparse_ids (set[str]): Chunk ids the sparse-only probe returned.
        """
        # 1. Union across calls so a ForEach over sub-queries still yields one breakdown at emit.
        self.dense_ids = dense_ids if self.dense_ids is None else (self.dense_ids | dense_ids)
        self.sparse_ids = sparse_ids if self.sparse_ids is None else (self.sparse_ids | sparse_ids)
        self.branch_probe_ok += 1

    def record_branch_error(self) -> None:
        """Record a failed branch probe — the search is unaffected, the breakdown is skipped."""
        # 1. Count the failure so an always-failing probe surfaces on its own counter.
        self.branch_probe_error += 1


__all__ = [
    "SearchRetrievalProbe",
    "AXES_DENSE_SPARSE",
    "AXES_DENSE_ONLY",
    "AXES_SPARSE_ONLY",
    "AXES_NONE",
]
