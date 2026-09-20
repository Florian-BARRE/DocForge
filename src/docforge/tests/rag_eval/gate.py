# ====== Code Summary ======
# The retrieval-quality regression gate. Two independent halves on purpose:
#   1. `compare()` — a PURE function (no I/O, no network) that judges a report against a committed
#      baseline. This is what makes the gate's own arithmetic unit-testable in the fast, serviceless
#      `tests/rag_eval` suite (collected by `gate.yml`'s "Retrieval-eval unit suite" step).
#   2. `RetrievalQualityGate` + `main()` — the live half: runs the deterministic SYNTHETIC regulatory
#      corpus (`tests/rag_eval/synthetic.py`, never QASPER — QASPER's HuggingFace fetch is a
#      network/determinism flake, developer-only) against a running stack on the product-default
#      pipeline, writes a machine-readable report, and exits non-zero on a gated regression. This half
#      is exercised ONLY by `.github/workflows/retrieval-quality.yml` (manual dispatch), never by the
#      fast CI gate.
#
# Gated metrics: hit@5, hit@10, MRR (0.05 absolute tolerance, overridable). hit@1 is REPORTED but never
# gated — on 48 queries a single rank-1/rank-2 flip moves it ~0.02, the jitteriest number in the ladder.
# Two INTEGRITY failures are distinguished from quality regressions (named, not silently folded into a
# metric miss): `ingested < papers` (an ingestion/worker failure, not a retrieval regression) and
# `n_queries` drift vs the baseline (the corpus itself changed — the baseline must be regenerated
# deliberately, never silently reinterpreted).

# ====== Standard Library Imports ======
import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from tests.rag_eval.harness import (
    BENCH_PREFIX,
    DocForgeClient,
    EvalReport,
    client_from_env,
    run_eval,
)
from tests.rag_eval.synthetic import load_regulatory_papers

# The tracked baseline this gate compares against by default — see D14 in the RPI plan: MUST live
# under `baselines/`, never under `tests/rag_eval/data/` (gitignored, would silently never commit).
_DEFAULT_BASELINE = Path(__file__).parent / "baselines" / "regulatory.json"

# Gated metrics regress the build; hit@1 is reported for visibility only (too jittery on 48 queries).
_GATED_METRICS = ("hit@5", "hit@10", "mrr")
_REPORTED_METRICS = ("hit@1", "hit@3", "hit@5", "hit@10", "mrr")


def _metric_value(report: dict, name: str) -> float:
    """
    Read one metric (``"hit@<k>"`` or ``"mrr"``) out of a report/baseline dict.

    Args:
        report (dict): A report or baseline dict shaped like `Report.to_dict()`.
        name (str): The metric name, e.g. ``"hit@5"`` or ``"mrr"``.

    Returns:
        float: The metric's value.

    Raises:
        KeyError: If the report/baseline is missing the field (a malformed file, not a regression).
    """
    if name == "mrr":
        return float(report["mrr"])
    k = name.split("@", 1)[1]
    return float(report["hit_at"][k])


@dataclass(frozen=True, slots=True)
class MetricCheck:
    """One gated-or-reported metric's current value vs its baseline."""

    name: str
    current: float
    baseline: float
    tolerance: float
    gated: bool
    passed: bool


@dataclass(frozen=True, slots=True)
class GateVerdict:
    """The full gate outcome: overall pass/fail, every metric checked, and any integrity failure."""

    passed: bool
    metrics: list[MetricCheck]
    integrity_errors: list[str]


def compare(current: dict, baseline: dict, tolerance: float) -> GateVerdict:
    """
    Judge a current retrieval-quality report against a committed baseline. PURE — no I/O.

    Args:
        current (dict): The just-produced report, shaped like `Report.to_dict()`.
        baseline (dict): The committed baseline, same shape (n_queries + hit_at + mrr required).
        tolerance (float): Absolute regression tolerance applied to every GATED metric.

    Returns:
        GateVerdict: Fails when any gated metric regresses beyond `tolerance`, or on an integrity
        failure (`ingested < papers`, or `n_queries` drift vs the baseline) — either of which is named
        explicitly rather than surfacing as a confusing metric miss.
    """
    # 1. Integrity checks — these are not quality regressions, so they get their own named errors.
    integrity_errors = _integrity_errors(current, baseline)

    # 2. Every reported metric, flagging which ones actually gate the verdict.
    metrics = [
        _check_metric(name, current, baseline, tolerance, gated=name in _GATED_METRICS)
        for name in _REPORTED_METRICS
    ]

    # 3. Overall verdict: no integrity failure AND every GATED metric within tolerance.
    passed = not integrity_errors and all(metric.passed for metric in metrics if metric.gated)
    return GateVerdict(passed=passed, metrics=metrics, integrity_errors=integrity_errors)


def _check_metric(
    name: str, current: dict, baseline: dict, tolerance: float, *, gated: bool
) -> MetricCheck:
    """Build one `MetricCheck`; non-gated metrics always `passed=True` (informational only)."""
    current_value = _metric_value(current, name)
    baseline_value = _metric_value(baseline, name)
    passed = True if not gated else current_value >= baseline_value - tolerance
    return MetricCheck(
        name=name,
        current=current_value,
        baseline=baseline_value,
        tolerance=tolerance,
        gated=gated,
        passed=passed,
    )


def _integrity_errors(current: dict, baseline: dict) -> list[str]:
    """Named integrity failures — ingestion incompleteness and corpus drift — never a metric miss."""
    errors: list[str] = []
    ingested, papers = current.get("ingested"), current.get("papers")
    if ingested is not None and papers is not None and ingested < papers:
        errors.append(
            f"ingestion incomplete: {ingested}/{papers} papers ingested — an ingestion/worker "
            "failure, not a retrieval regression"
        )
    current_n, baseline_n = current.get("n_queries"), baseline.get("n_queries")
    if current_n is not None and baseline_n is not None and current_n != baseline_n:
        errors.append(
            f"corpus drift: current run has {current_n} queries, baseline expects {baseline_n} — "
            "regenerate the baseline deliberately with --update-baseline, don't reinterpret it"
        )
    return errors


@dataclass(slots=True)
class Report:
    """The machine-readable retrieval-quality report — the shape both the file and `compare()` share."""

    corpus: str
    n_queries: int
    papers: int
    ingested: int
    hit_at: dict[str, float]
    mrr: float
    generated_at: str
    git_sha: str
    seeded: bool = False
    note: str = ""

    def to_dict(self) -> dict:
        """JSON-serializable dict — what gets written to `--out` and to the baseline file."""
        return {
            "corpus": self.corpus,
            "n_queries": self.n_queries,
            "papers": self.papers,
            "ingested": self.ingested,
            "hit_at": self.hit_at,
            "mrr": self.mrr,
            "generated_at": self.generated_at,
            "git_sha": self.git_sha,
            "seeded": self.seeded,
            "note": self.note,
        }

    @classmethod
    def from_eval(cls, evaluated: EvalReport, *, corpus: str, git_sha: str) -> "Report":
        """Build a `Report` from the harness's `EvalReport` (adds provenance: timestamp + git sha)."""
        return cls(
            corpus=corpus,
            n_queries=evaluated.metrics.n_queries,
            papers=evaluated.papers,
            ingested=evaluated.ingested,
            hit_at={str(k): v for k, v in evaluated.metrics.hit_at.items()},
            mrr=evaluated.metrics.mrr,
            generated_at=datetime.now(UTC).isoformat(),
            git_sha=git_sha,
        )


@dataclass(slots=True)
class GateConfig:
    """CLI-facing knobs for one gate run."""

    papers: int = 6
    tolerance: float = 0.05
    out: Path | None = None
    baseline: Path = field(default_factory=lambda: _DEFAULT_BASELINE)
    update_baseline: bool = False


class RetrievalQualityGate(LoggerClass):
    """Runs the synthetic regulatory corpus against a live stack and gates it vs a committed baseline."""

    def __init__(self, config: GateConfig) -> None:
        LoggerClass.__init__(self)
        self._config = config

    def run(self) -> int:
        """
        Run the eval end to end and return the process exit code.

        Returns:
            int: 0 when the gate passes (or `--update-baseline` was requested), 1 on a gated
            regression or integrity failure, 2 when the stack is unreachable.
        """
        # 1. A reachable, authenticated client is a prerequisite — fail fast and loudly if absent.
        client = client_from_env()
        if client is None:
            self.logger.error(
                f"DOCFORGE_TOKEN is unset or the API is unreachable — export it and start the stack"
            )
            return 2

        # 2. Run the product-default pipeline over the full deterministic corpus.
        try:
            report = self._run_eval(client)
        finally:
            client.close()

        # 3. Persist the report when asked (the workflow always asks, for the uploaded artifact).
        if self._config.out is not None:
            self._config.out.write_text(json.dumps(report.to_dict(), indent=2) + "\n")

        # 4. `--update-baseline` writes and stops — a human reviews and commits it, CI never passes it.
        if self._config.update_baseline:
            self._config.baseline.write_text(json.dumps(report.to_dict(), indent=2) + "\n")
            self.logger.info(f"Baseline written to {self._config.baseline} — review and commit it")
            return 0

        # 5. Compare against the committed baseline and print a human-readable verdict.
        baseline = json.loads(self._config.baseline.read_text())
        verdict = compare(report.to_dict(), baseline, self._config.tolerance)
        self._print_verdict(report, verdict)
        return 0 if verdict.passed else 1

    def _run_eval(self, client: DocForgeClient) -> Report:
        """Ingest the synthetic regulatory corpus and score retrieval on the product default pipeline."""
        papers = load_regulatory_papers(self._config.papers)
        self.logger.info(f"Loaded {len(papers)} synthetic regulatory documents")
        client.purge_by_prefix(BENCH_PREFIX)
        evaluated = run_eval(
            client,
            papers,
            label="retrieval-quality-gate",
            corpus="regulatory",
            ks=(1, 3, 5, 10),
            search_limit=10,
            keep_collection=False,
        )
        return Report.from_eval(evaluated, corpus="regulatory", git_sha=self._git_sha())

    @staticmethod
    def _git_sha() -> str:
        """The current commit — best-effort provenance, never fatal when git is unavailable."""
        try:
            return subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return "unknown"

    def _print_verdict(self, report: Report, verdict: GateVerdict) -> None:
        """Human-readable summary — mirrors `runner.py`'s `_print_report` console-table convention."""
        ladder = "  ".join(
            f"{m.name}={m.current:.3f}"
            f"{' (gated, baseline=' + format(m.baseline, '.3f') + ')' if m.gated else ' (reported)'}"
            for m in verdict.metrics
        )
        print(
            f"\n[retrieval-quality] corpus={report.corpus} papers={report.ingested}/{report.papers} "
            f"queries={report.n_queries} git_sha={report.git_sha}"
        )
        print(f"    {ladder}")
        for error in verdict.integrity_errors:
            print(f"    INTEGRITY FAILURE: {error}")
        print(f"    VERDICT: {'PASS' if verdict.passed else 'FAIL'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Retrieval-quality regression gate (deterministic synthetic regulatory corpus)."
    )
    parser.add_argument(
        "--papers", type=int, default=6, help="Synthetic regulations to ingest (max 6, default 6)."
    )
    parser.add_argument("--out", type=Path, default=None, help="Write the JSON report here.")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=_DEFAULT_BASELINE,
        help="Baseline JSON to compare against (default: tests/rag_eval/baselines/regulatory.json).",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.05,
        help="Absolute regression tolerance for the gated metrics (hit@5/hit@10/MRR).",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Overwrite --baseline with this run's numbers. Human-reviewed-commit only — CI never "
        "passes this flag.",
    )
    args = parser.parse_args(argv)

    config = GateConfig(
        papers=args.papers,
        tolerance=args.tolerance,
        out=args.out,
        baseline=args.baseline,
        update_baseline=args.update_baseline,
    )
    return RetrievalQualityGate(config).run()


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "compare",
    "GateVerdict",
    "MetricCheck",
    "Report",
    "GateConfig",
    "RetrievalQualityGate",
    "main",
]
