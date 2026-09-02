# ====== Code Summary ======
# CLI entry point for the RAG benchmark — the thing an agent (or you) runs to get real numbers. It
# loads a QASPER slice, then evaluates retrieval under one or more CHUNK configs and prints a table
# of hit@k + MRR so the effect of structure-aware granularity (min_tokens/target_tokens) is measured
# on data, not guessed. Zero LLM/VLM cost: the default pipeline embeds locally with BGE-M3. Usage:
#
#   DOCFORGE_TOKEN=$(docker compose -f compose/dev-cpu.yml \
#       exec -T docforge_app printenv AUTH_ROOT_TOKEN | tr -d '\r') \
#     uv run python -m tests.rag_eval.runner --papers 150 --sweep
#
# --sweep compares the product default against strict one-chunk-per-section (min_tokens=0).

# ====== Standard Library Imports ======
import argparse
import sys

# ====== Local Project Imports ======
from tests.rag_eval.harness import BENCH_PREFIX, EvalReport, client_from_env, run_eval
from tests.rag_eval.qasper import load_papers
from tests.rag_eval.synthetic import load_regulatory_papers


def _print_report(report: EvalReport) -> None:
    """One line block per config: counts + the hit@k ladder + MRR."""
    metrics = report.metrics
    ladder = "  ".join(f"hit@{k}={metrics.hit_at[k]:.3f}" for k in sorted(metrics.hit_at))
    print(
        f"\n[{report.label}] papers={report.ingested}/{report.papers} "
        f"questions={report.questions}  collection={report.collection_id}"
    )
    print(f"    {ladder}  MRR={metrics.mrr:.3f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DocForge RAG retrieval benchmark (QASPER).")
    parser.add_argument("--papers", type=int, default=8, help="Documents to ingest (slice).")
    parser.add_argument(
        "--corpus",
        choices=("qasper", "regulatory"),
        default="qasper",
        help="qasper = long prose papers (retrieval quality); "
        "regulatory = short-clause synthetic docs (chunk-granularity sensitivity).",
    )
    parser.add_argument("--limit", type=int, default=10, help="Chunks retrieved per query.")
    parser.add_argument(
        "--min-tokens", type=int, default=None, help="Override chunk min_tokens (single run)."
    )
    parser.add_argument(
        "--target-tokens", type=int, default=None, help="Override chunk target_tokens (single run)."
    )
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="Compare the product default vs strict per-section chunking (min_tokens=0).",
    )
    args = parser.parse_args(argv)

    client = client_from_env()
    if client is None:
        print(
            "DOCFORGE_TOKEN is unset or the API is unreachable. Export the token and start the "
            "stack, then re-run (see the module docstring).",
            file=sys.stderr,
        )
        return 2

    purged = client.purge_by_prefix(BENCH_PREFIX)
    if purged:
        print(f"Purged {purged} prior benchmark collection(s).")

    papers = (
        load_regulatory_papers(args.papers)
        if args.corpus == "regulatory"
        else load_papers(args.papers)
    )
    print(
        f"Loaded {len(papers)} {args.corpus} documents "
        f"({sum(len(p.questions) for p in papers)} answerable questions)."
    )

    ks = (1, 3, 5, 10)
    if args.sweep:
        configs = [
            ("chunk défaut (min=64)", None, None),
            ("chunk strict (1 section=1 chunk)", 0, args.target_tokens),
        ]
    else:
        label = f"min={args.min_tokens},target={args.target_tokens}"
        configs = [(label, args.min_tokens, args.target_tokens)]

    corpus_tag = "réglementaire" if args.corpus == "regulatory" else "qasper"
    for label, min_tokens, target_tokens in configs:
        report = run_eval(
            client,
            papers,
            label=label,
            corpus=corpus_tag,
            min_tokens=min_tokens,
            target_tokens=target_tokens,
            ks=ks,
            search_limit=args.limit,
        )
        _print_report(report)

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
