"""SearchHealthReader folds the docforge_search_* series into the cockpit tile. Covers the pure
quantile-from-buckets helper (known buckets → expected boundary, including the +Inf-overflow fallback)
and the summary math (zeros/None when nothing has run; error/zero-result rates + avg_hits + p95 on
seeded, ISOLATED collectors — never the process-global default registry, which other tests dirty)."""

import math

from prometheus_client import CollectorRegistry, Counter, Histogram

from backend.libs.metrics.search_health import SearchHealthReader


class _Metrics:
    """A fresh SearchMetrics-shaped holder on its OWN registry (isolated from the global default)."""

    def __init__(self) -> None:
        registry = CollectorRegistry()
        self.RUNS_TOTAL = Counter("docforge_search_runs_total", "d", ["outcome"], registry=registry)
        self.ZERO_RESULT_TOTAL = Counter(
            "docforge_search_zero_result_total", "d", registry=registry
        )
        self.RUN_DURATION_SECONDS = Histogram(
            "docforge_search_run_duration_seconds",
            "d",
            buckets=(0.005, 0.01, 0.05, 0.1, 0.5, 1.0),
            registry=registry,
        )
        self.HITS = Histogram(
            "docforge_search_hits", "d", buckets=(0, 1, 2, 3, 5, 10), registry=registry
        )


# ---------------------- Pure quantile helper ---------------------- #
def test_quantile_returns_none_without_observations() -> None:
    """No observations → no quantile to report (None, never a fabricated 0)."""
    assert (
        SearchHealthReader.quantile_from_buckets([(1.0, 0.0), (math.inf, 0.0)], 0.0, 0.95) is None
    )


def test_quantile_picks_the_first_boundary_that_crosses_the_rank() -> None:
    """p95 of 10 obs (rank 9.5) → the smallest boundary whose cumulative count reaches it."""
    buckets = [(1.0, 5.0), (2.0, 10.0), (math.inf, 10.0)]
    assert SearchHealthReader.quantile_from_buckets(buckets, 10.0, 0.95) == 2.0


def test_quantile_crosses_in_the_first_bucket() -> None:
    """When the whole mass is in the first bucket, that boundary is the quantile."""
    buckets = [(1.0, 10.0), (2.0, 10.0), (math.inf, 10.0)]
    assert SearchHealthReader.quantile_from_buckets(buckets, 10.0, 0.95) == 1.0


def test_quantile_falls_back_to_largest_finite_boundary_on_inf_overflow() -> None:
    """When the crossing sits in the +Inf overflow bucket, return the largest finite boundary."""
    buckets = [(1.0, 3.0), (2.0, 4.0), (math.inf, 10.0)]
    assert SearchHealthReader.quantile_from_buckets(buckets, 10.0, 0.95) == 2.0


# ---------------------- Summary roll-up ---------------------- #
def test_summary_is_all_zero_and_none_when_nothing_has_run() -> None:
    """A cold process reports zero rates and null latency/mean — never a divide-by-zero or a made-up 0."""
    summary = SearchHealthReader.summary(_Metrics())
    assert summary.total_runs == 0
    assert summary.error_rate == 0.0
    assert summary.zero_result_rate == 0.0
    assert summary.p95_latency_ms is None
    assert summary.avg_hits is None


def test_summary_computes_rates_p95_and_avg_hits_from_seeded_series() -> None:
    """Error/zero-result rates, avg_hits and p95 latency are read straight off the seeded collectors."""
    # 1. Seed 10 runs: 6 success + 2 failed + 1 timeout + 1 unavailable (→ 4 errors).
    metrics = _Metrics()
    metrics.RUNS_TOTAL.labels(outcome="success").inc(6)
    metrics.RUNS_TOTAL.labels(outcome="failed").inc(2)
    metrics.RUNS_TOTAL.labels(outcome="timeout").inc(1)
    metrics.RUNS_TOTAL.labels(outcome="unavailable").inc(1)

    # 2. Two of them delivered zero hits.
    metrics.ZERO_RESULT_TOTAL.inc(2)

    # 3. Run-duration: nine fast (0.02s) + one slow (0.8s) → p95 rank 9.5 lands in the le=1.0 bucket.
    for _ in range(9):
        metrics.RUN_DURATION_SECONDS.observe(0.02)
    metrics.RUN_DURATION_SECONDS.observe(0.8)

    # 4. Hits over successful runs: 0 + 4 + 8 → mean 4.0.
    for hit_count in (0, 4, 8):
        metrics.HITS.observe(hit_count)

    summary = SearchHealthReader.summary(metrics)
    assert summary.total_runs == 10
    assert summary.error_rate == 0.4
    assert summary.zero_result_rate == 0.2
    assert summary.avg_hits == 4.0
    assert summary.p95_latency_ms == 1000.0
