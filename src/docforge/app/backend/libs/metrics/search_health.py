# ====== Code Summary ======
# SearchHealthReader — the app-side READ counterpart of SearchMetricsEmitter. The emitter WRITES the
# docforge_search_* series; this reader reads their CURRENT values (via prometheus_client's
# .collect() samples) and folds them into the small, tile-friendly SearchHealthSummary the deployment
# Overview cockpit polls. It keeps NO parallel counters of its own — the emitted series are the single
# source of truth, so the tile can never disagree with Grafana.
#
# p95 is a classic bucket-based histogram_quantile approximation on the run-duration histogram's FIXED
# buckets (no interpolation): the smallest bucket boundary whose cumulative count reaches 0.95 x the
# histogram's own observation count. The source holder is injectable so the pure math can be unit
# tested against isolated collectors without touching the process-global default registry.

# ====== Standard Library Imports ======
import math

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus
from prometheus_client.metrics import MetricWrapperBase

# ====== Local Project Imports ======
from ...routers.search.models import SearchHealthSummary
from .search_collectors import SearchMetrics

# The run outcomes that count as an error for the health tile (the runner emits exactly these plus
# "success" — see SearchRunner.run). Named explicitly so the error rate matches the documented
# contract rather than silently reclassifying a future non-error outcome.
_ERROR_OUTCOMES = frozenset({"failed", "timeout", "unavailable"})

# The latency percentile the tile surfaces.
_P95 = 0.95


class SearchHealthReader:
    """Static reader that folds the docforge_search_* series into a SearchHealthSummary tile."""

    logger = loggerplusplus.bind(identifier="SearchHealthReader")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SearchHealthReader is a static-only class and cannot be instantiated.")

    @classmethod
    def __counter_by_label(cls, metric: MetricWrapperBase, label: str) -> dict[str, float]:
        """Read a labelled counter's current value per label value (skipping the _created gauge)."""
        # 1. The real counter sample name ends in _total; _created is a separate birth-time gauge.
        result: dict[str, float] = {}
        for family in metric.collect():
            for sample in family.samples:
                if sample.name.endswith("_total") and label in sample.labels:
                    result[sample.labels[label]] = sample.value
        return result

    @classmethod
    def __single_counter(cls, metric: MetricWrapperBase) -> float:
        """Read an unlabelled counter's current value (its _total sample)."""
        # 1. First _total sample is the whole value for an unlabelled counter.
        for family in metric.collect():
            for sample in family.samples:
                if sample.name.endswith("_total"):
                    return sample.value
        return 0.0

    @classmethod
    def __histogram_buckets(
        cls, metric: MetricWrapperBase
    ) -> tuple[list[tuple[float, float]], float]:
        """Read a histogram's cumulative (le, count) buckets and its total observation count."""
        # 1. Split the _bucket samples (with their le boundary) from the _count sample.
        buckets: list[tuple[float, float]] = []
        count = 0.0
        for family in metric.collect():
            for sample in family.samples:
                if sample.name.endswith("_bucket"):
                    le = sample.labels.get("le", "+Inf")
                    boundary = math.inf if le in ("+Inf", "Inf") else float(le)
                    buckets.append((boundary, sample.value))
                elif sample.name.endswith("_count"):
                    count = sample.value
        # 2. Prometheus buckets are cumulative and ascending; sort defensively.
        buckets.sort(key=lambda item: item[0])
        return buckets, count

    @classmethod
    def __histogram_sum_count(cls, metric: MetricWrapperBase) -> tuple[float, float]:
        """Read a histogram's running _sum and _count (the basis for its mean)."""
        # 1. Pick the two aggregate samples off the collected family.
        total_sum = 0.0
        count = 0.0
        for family in metric.collect():
            for sample in family.samples:
                if sample.name.endswith("_sum"):
                    total_sum = sample.value
                elif sample.name.endswith("_count"):
                    count = sample.value
        return total_sum, count

    @classmethod
    def quantile_from_buckets(
        cls, buckets: list[tuple[float, float]], total: float, quantile: float
    ) -> float | None:
        """
        Approximate a latency quantile from fixed histogram buckets (no interpolation).

        Classic ``histogram_quantile`` on cumulative buckets: the smallest bucket BOUNDARY whose
        cumulative count reaches ``quantile x total``. When the crossing sits in the ``+Inf`` overflow
        bucket, the largest finite boundary is returned as the best available upper bound.

        Args:
            buckets (list[tuple[float, float]]): ``(le, cumulative_count)`` pairs, ascending by ``le``
                (``le`` may be ``inf`` for the overflow bucket).
            total (float): The histogram's total observation count.
            quantile (float): The target quantile in [0, 1].

        Returns:
            float | None: The bucket boundary (same unit as ``le``), or None when there is no data.
        """
        # 1. No observations → no quantile to report.
        if total <= 0:
            return None

        # 2. The rank the quantile falls on.
        rank = quantile * total

        # 3. First finite boundary whose cumulative count reaches the rank.
        finite = [(le, count) for le, count in buckets if math.isfinite(le)]
        for le, cumulative in finite:
            if cumulative >= rank:
                return le

        # 4. The crossing is in the +Inf bucket → the largest finite boundary is the best bound.
        return finite[-1][0] if finite else None

    @classmethod
    def summary(cls, source: type[SearchMetrics] = SearchMetrics) -> SearchHealthSummary:
        """
        Fold the current docforge_search_* series into the tile-friendly SearchHealthSummary.

        Args:
            source (type[SearchMetrics]): The metric holder to read (defaults to the process-global
                ``SearchMetrics``; injectable so the math is unit-testable against isolated series).

        Returns:
            SearchHealthSummary: Cumulative-since-start totals, rates and latency for the cockpit tile.
        """
        # 1. Outcome counts drive the run total and the error rate.
        outcomes = cls.__counter_by_label(source.RUNS_TOTAL, "outcome")
        total = sum(outcomes.values())
        errors = sum(value for name, value in outcomes.items() if name in _ERROR_OUTCOMES)

        # 2. Zero-result share of all runs.
        zero_results = cls.__single_counter(source.ZERO_RESULT_TOTAL)

        # 3. p95 whole-run latency from the run-duration histogram buckets (seconds → ms).
        buckets, run_count = cls.__histogram_buckets(source.RUN_DURATION_SECONDS)
        p95_seconds = cls.quantile_from_buckets(buckets, run_count, _P95)

        # 4. Mean delivered hits from the hits histogram (_sum / _count over successful runs).
        hits_sum, hits_count = cls.__histogram_sum_count(source.HITS)

        # 5. Fold into the tile — rates are 0.0 with no runs, latency/mean are None with no data.
        return SearchHealthSummary(
            total_runs=int(total),
            error_rate=(errors / total) if total else 0.0,
            p95_latency_ms=(p95_seconds * 1000.0) if p95_seconds is not None else None,
            zero_result_rate=(zero_results / total) if total else 0.0,
            avg_hits=(hits_sum / hits_count) if hits_count else None,
        )


__all__ = ["SearchHealthReader"]
