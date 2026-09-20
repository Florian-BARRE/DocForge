"""Unit tests for the retrieval-quality gate's PURE `compare()` — no network/stack. Run with:
`uv run pytest tests/rag_eval/test_gate.py -m "not live"`."""

import json

from tests.rag_eval.gate import GateVerdict, Report, compare

_BASELINE = {
    "corpus": "regulatory",
    "n_queries": 48,
    "papers": 6,
    "ingested": 6,
    "hit_at": {"1": 0.50, "3": 0.70, "5": 0.80, "10": 0.90},
    "mrr": 0.60,
}


def _current(**overrides: object) -> dict:
    """A current report identical to the baseline, with the given fields overridden."""
    current = json.loads(json.dumps(_BASELINE))  # deep copy without importing copy
    current.update(overrides)
    return current


def test_pass_when_current_matches_baseline_exactly() -> None:
    verdict = compare(_current(), _BASELINE, tolerance=0.05)
    assert verdict.passed
    assert not verdict.integrity_errors
    assert all(metric.passed for metric in verdict.metrics)


def test_pass_when_regression_is_just_inside_tolerance() -> None:
    # hit@5 drops from 0.80 to 0.76 — a 0.04 regression, under the 0.05 tolerance.
    current = _current(hit_at={"1": 0.50, "3": 0.70, "5": 0.76, "10": 0.90})
    verdict = compare(current, _BASELINE, tolerance=0.05)
    assert verdict.passed


def test_fail_when_regression_is_just_outside_tolerance() -> None:
    # hit@5 drops from 0.80 to 0.74 — a 0.06 regression, over the 0.05 tolerance.
    current = _current(hit_at={"1": 0.50, "3": 0.70, "5": 0.74, "10": 0.90})
    verdict = compare(current, _BASELINE, tolerance=0.05)
    assert not verdict.passed
    assert not verdict.integrity_errors  # a metric miss, not an integrity failure
    hit5 = next(m for m in verdict.metrics if m.name == "hit@5")
    assert hit5.gated and not hit5.passed


def test_hit_at_1_is_reported_but_never_gates_the_verdict() -> None:
    # hit@1 collapses to 0.0 — a huge drop — but the gate must still PASS on it alone.
    current = _current(hit_at={"1": 0.0, "3": 0.70, "5": 0.80, "10": 0.90})
    verdict = compare(current, _BASELINE, tolerance=0.05)
    assert verdict.passed
    hit1 = next(m for m in verdict.metrics if m.name == "hit@1")
    assert not hit1.gated
    assert hit1.passed  # informational metrics always report passed=True


def test_fail_on_ingestion_incomplete() -> None:
    current = _current(ingested=4)  # papers=6, so 4/6 ingested
    verdict = compare(current, _BASELINE, tolerance=0.05)
    assert not verdict.passed
    assert any("ingestion incomplete" in error for error in verdict.integrity_errors)


def test_fail_on_corpus_drift() -> None:
    current = _current(n_queries=40)  # baseline expects 48
    verdict = compare(current, _BASELINE, tolerance=0.05)
    assert not verdict.passed
    assert any("corpus drift" in error for error in verdict.integrity_errors)


def test_integrity_failure_does_not_mask_a_healthy_metric_ladder() -> None:
    # Metrics are all healthy, but ingestion failed — the verdict must still fail, on the right cause.
    current = _current(ingested=5)
    verdict = compare(current, _BASELINE, tolerance=0.05)
    assert not verdict.passed
    assert all(metric.passed for metric in verdict.metrics if metric.gated)
    assert verdict.integrity_errors


def test_report_to_dict_round_trips_through_compare() -> None:
    report = Report(
        corpus="regulatory",
        n_queries=48,
        papers=6,
        ingested=6,
        hit_at={"1": 0.5, "3": 0.7, "5": 0.8, "10": 0.9},
        mrr=0.6,
        generated_at="2026-09-20T00:00:00+00:00",
        git_sha="deadbeef",
    )
    payload = json.loads(json.dumps(report.to_dict()))  # simulate a --out file round-trip
    verdict = compare(payload, _BASELINE, tolerance=0.05)
    assert isinstance(verdict, GateVerdict)
    assert verdict.passed
