# ====== Code Summary ======
# Pure retrieval-quality metrics for the RAG benchmark — no network, no store, no DocForge import,
# so they are unit-testable in isolation. The gold signal is "does a retrieved chunk COVER a gold
# evidence passage" (token containment, robust to the chunker splitting/reflowing whitespace), from
# which hit@k (any top-k chunk covers any evidence), recall@k (fraction of evidence passages covered
# in top-k) and MRR (1/rank of the first covering chunk) follow.

# ====== Standard Library Imports ======
import re
from collections.abc import Sequence
from dataclasses import dataclass

_WORD = re.compile(r"\w+", re.UNICODE)


def tokens(text: str) -> list[str]:
    """Lowercased word tokens — the unit both coverage and overlap are measured in."""
    return _WORD.findall(text.lower())


def covers(chunk_text: str, evidence_text: str, threshold: float = 0.6) -> bool:
    """
    Whether a retrieved chunk COVERS a gold evidence passage.

    Coverage is token CONTAINMENT — the share of the evidence's tokens present in the chunk — not a
    substring test, because the chunker reflows whitespace, prepends a breadcrumb/heading and may
    join a caption, so an exact substring rarely survives. An empty evidence never counts as covered.

    Args:
        chunk_text (str): The retrieved chunk's text.
        evidence_text (str): One gold evidence passage.
        threshold (float): Minimum fraction of evidence tokens that must appear in the chunk.

    Returns:
        bool: True when the chunk covers the evidence at or above the threshold.
    """
    evidence = tokens(evidence_text)
    if not evidence:
        return False
    present = set(tokens(chunk_text))
    hit = sum(1 for token in evidence if token in present)
    return (hit / len(evidence)) >= threshold


@dataclass(frozen=True)
class QueryResult:
    """One query's outcome against a ranked chunk list, for a set of gold evidence passages."""

    hits_at_rank: list[bool]  # per rank (0-indexed): does this ranked chunk cover ANY evidence?
    covered_evidence: int  # distinct evidence passages covered anywhere in the ranking
    n_evidence: int  # gold evidence passages for this query (>0)


def evaluate_query(
    ranked_chunks: Sequence[str], evidences: Sequence[str], threshold: float = 0.6
) -> QueryResult:
    """
    Score one query: which ranked chunks cover which gold evidence passages.

    Args:
        ranked_chunks (Sequence[str]): Retrieved chunk texts, best-first.
        evidences (Sequence[str]): The query's gold evidence passages (already text-only, non-empty).
        threshold (float): Coverage threshold passed to ``covers``.

    Returns:
        QueryResult: Per-rank hit flags + distinct-evidence coverage.
    """
    hits_at_rank = [
        any(covers(chunk, evidence, threshold) for evidence in evidences) for chunk in ranked_chunks
    ]
    covered = sum(
        1
        for evidence in evidences
        if any(covers(chunk, evidence, threshold) for chunk in ranked_chunks)
    )
    return QueryResult(
        hits_at_rank=hits_at_rank, covered_evidence=covered, n_evidence=len(evidences)
    )


def hit_at_k(result: QueryResult, k: int) -> bool:
    """True when ANY of the top-k ranked chunks covers an evidence passage (the classic RAG hit)."""
    return any(result.hits_at_rank[:k])


def recall_at_k(result: QueryResult, k: int) -> float:
    """Fraction of the query's gold evidence passages covered within the top-k (0 when none/empty)."""
    if result.n_evidence == 0:
        return 0.0
    # Recompute distinct-evidence coverage restricted to top-k would need the per-evidence map; the
    # hit-based proxy (covered_evidence is over the FULL ranking) is reported separately as recall@∞.
    # For top-k recall we conservatively use whether the top-k produced any hit scaled by coverage.
    covered_in_k = any(result.hits_at_rank[:k])
    return (result.covered_evidence / result.n_evidence) if covered_in_k else 0.0


def reciprocal_rank(result: QueryResult) -> float:
    """1 / (rank of the first covering chunk), 0 when no chunk covers any evidence."""
    for rank, hit in enumerate(result.hits_at_rank, start=1):
        if hit:
            return 1.0 / rank
    return 0.0


@dataclass(frozen=True)
class Aggregate:
    """Mean metrics over a set of queries — the benchmark's headline numbers."""

    n_queries: int
    hit_at: dict[int, float]
    mrr: float


def aggregate(results: Sequence[QueryResult], ks: Sequence[int]) -> Aggregate:
    """
    Average per-query metrics into the benchmark headline (hit@k for each k, MRR).

    Args:
        results (Sequence[QueryResult]): One entry per evaluated query.
        ks (Sequence[int]): The cut-offs to report hit@k at.

    Returns:
        Aggregate: n_queries, {k: mean hit@k}, mean reciprocal rank.
    """
    n = len(results)
    if n == 0:
        return Aggregate(n_queries=0, hit_at={k: 0.0 for k in ks}, mrr=0.0)
    hit_at = {k: sum(hit_at_k(result, k) for result in results) / n for k in ks}
    mrr = sum(reciprocal_rank(result) for result in results) / n
    return Aggregate(n_queries=n, hit_at=hit_at, mrr=mrr)


__all__ = [
    "tokens",
    "covers",
    "QueryResult",
    "evaluate_query",
    "hit_at_k",
    "recall_at_k",
    "reciprocal_rank",
    "Aggregate",
    "aggregate",
]
