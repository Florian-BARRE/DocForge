# ====== Code Summary ======
# SearchMetrics — the per-search Prometheus series (docforge_search_*), a static holder that creates
# every series once at import time on the DEFAULT prometheus_client registry. It lives beside the
# SEARCH pipeline's app-side boundary and is fed exclusively by SearchMetricsEmitter (the runner
# never touches prometheus_client directly, a node never sees this file). Because the series sit on
# the same default registry as DocForgeMetrics, the existing MetricsService.render() / generate_latest()
# renders them together with no MetricsService change and no compose change — METRICS_ENABLED still
# gates EXPOSURE at /metrics; emission always feeds. A separate file from collectors.py on purpose:
# folding these ~12 series in would more than double that file past general.md's ~150-line signal.
#
# Cardinality is bounded BY DESIGN: the only per-series label is `stage` (the registry FAMILY, one of
# the 7 search families + "unknown"), never a node_id or collection_id — a stored search blob names
# its nodes arbitrarily, so a node_id label would be a user-controlled cardinality leak. In
# particular, docforge_search_retrieval_total{axes="none", filtered=...} is the scrapable reading of
# a "filter-only" retrieval: the case where the target vectors resolved to nothing and the port
# returned [] — today an invisible degradation, here a first-class series.

# ====== Third-Party Library Imports ======
from prometheus_client import Counter, Histogram

# A sub-second-oriented ladder — search is sub-second by design, so prometheus_client's default
# buckets would bunch nearly everything into the first two.
_LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

# A [0, 1] share ladder for the branch-contribution ratios (a fraction of the fused pool).
_RATIO_BUCKETS = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)


class SearchMetrics:
    """Static holder of every per-search Prometheus series (each created once, at import time)."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SearchMetrics is a static-only class and cannot be instantiated.")

    # ── Run-level outcome + latency ────────────────────────────────────────────
    RUNS_TOTAL = Counter(
        "docforge_search_runs_total",
        "Search runs by outcome (a RUNNER run — the router can 4xx before a run ever starts).",
        ["outcome"],
    )
    RUN_DURATION_SECONDS = Histogram(
        "docforge_search_run_duration_seconds",
        "Whole-run search latency in seconds (the root execution record's duration).",
        buckets=_LATENCY_BUCKETS,
    )
    DURATION_SECONDS = Histogram(
        "docforge_search_duration_seconds",
        "Per-stage search latency in seconds, labelled by the node's registry family.",
        ["stage"],
        buckets=_LATENCY_BUCKETS,
    )

    # ── Outcome / shape counters (success only, unless noted) ───────────────────
    HITS = Histogram(
        "docforge_search_hits",
        "Delivered hit count per successful search.",
        buckets=(0, 1, 2, 3, 5, 10, 20, 50, 100),
    )
    CANDIDATES = Histogram(
        "docforge_search_candidates",
        "Retrieved candidate count per search, summed over all retrieval calls.",
        buckets=(0, 1, 5, 10, 25, 50, 100, 250, 500, 1000),
    )
    ZERO_RESULT_TOTAL = Counter(
        "docforge_search_zero_result_total",
        "Successful searches that delivered zero hits.",
    )
    DEGRADED_TOTAL = Counter(
        "docforge_search_degraded_total",
        "Successful searches delivered on a degraded axis (an encode axis was unavailable).",
    )
    RETRIEVAL_TOTAL = Counter(
        "docforge_search_retrieval_total",
        "Retrieval calls by which axes were queried and whether a structured filter was applied.",
        ["axes", "filtered"],
    )

    # ── Rerank effect (rank displacement, not a raw — incomparable — score delta) ─
    RERANK_APPLIED_TOTAL = Counter(
        "docforge_search_rerank_applied_total",
        "Searches in which a rerank-family node ran.",
    )
    RERANK_RANK_SHIFT = Histogram(
        "docforge_search_rerank_rank_shift",
        "Mean absolute rank displacement of the delivered hits vs their retrieval rank (rerank on).",
        buckets=(0, 1, 2, 3, 5, 10, 20, 50),
    )

    # ── Opt-in dense/sparse fusion breakdown (slice 1B; OFF by default per collection) ─
    BRANCH_CONTRIBUTION_RATIO = Histogram(
        "docforge_search_branch_contribution_ratio",
        "Share of the fused candidate pool attributable to a single retrieval branch.",
        ["branch"],
        buckets=_RATIO_BUCKETS,
    )
    BRANCH_PROBE_TOTAL = Counter(
        "docforge_search_branch_probe_total",
        "Opt-in dense/sparse branch probes by outcome (so an always-failing probe is never silent).",
        ["outcome"],
    )


__all__ = ["SearchMetrics"]
