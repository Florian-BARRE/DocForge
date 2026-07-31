"""Unit tests for the RAG-benchmark metrics — pure, no network/stack. Run with:
`uv run pytest tests/rag_eval/test_metrics.py`."""

from tests.rag_eval.metrics import (
    aggregate,
    covers,
    evaluate_query,
    hit_at_k,
    reciprocal_rank,
    tokens,
)


def test_covers_is_token_containment_not_substring() -> None:
    evidence = "The edge load balancer performs TLS termination."
    # Reflowed + breadcrumb-prefixed chunk (no exact substring), but all evidence tokens present.
    chunk = "Networking Guide > Section 3\n\nAt the edge, the load balancer performs TLS termination now."
    assert covers(chunk, evidence, threshold=0.6)
    # A chunk sharing only a couple of common words does not cover it.
    assert not covers("Unrelated text about databases and indexes.", evidence, threshold=0.6)


def test_covers_empty_evidence_is_never_covered() -> None:
    assert not covers("anything at all", "", threshold=0.6)
    assert not covers("anything", "   ", threshold=0.6)


def test_covers_threshold_boundary() -> None:
    evidence = "alpha beta gamma delta"  # 4 tokens
    assert covers("alpha beta gamma zeta", evidence, threshold=0.75)  # 3/4 present
    assert not covers("alpha beta zeta zeta", evidence, threshold=0.75)  # 2/4 present


def test_evaluate_query_hit_recall_and_rank() -> None:
    evidences = ["cats purr loudly", "dogs bark at night"]
    ranked = [
        "an unrelated chunk about finance",  # rank 1: no cover
        "the cats purr loudly in the sun",  # rank 2: covers evidence 1
        "at night the dogs bark",  # rank 3: covers evidence 2
    ]
    result = evaluate_query(ranked, evidences, threshold=0.6)
    assert result.hits_at_rank == [False, True, True]
    assert result.covered_evidence == 2 and result.n_evidence == 2
    assert hit_at_k(result, 1) is False  # top-1 misses
    assert hit_at_k(result, 2) is True  # top-2 catches the first evidence
    assert reciprocal_rank(result) == 0.5  # first hit at rank 2


def test_aggregate_means_over_queries() -> None:
    # q1: first hit at rank 1 (RR=1, hit@1=1). q2: first hit at rank 3 (RR=1/3, hit@1=0, hit@5=1).
    q1 = evaluate_query(["cats purr loudly"], ["cats purr loudly"])
    q2 = evaluate_query(["x", "y", "dogs bark at night"], ["dogs bark at night"], threshold=0.6)
    agg = aggregate([q1, q2], ks=[1, 5])
    assert agg.n_queries == 2
    assert agg.hit_at[1] == 0.5  # only q1 hits at 1
    assert agg.hit_at[5] == 1.0  # both hit within 5
    assert abs(agg.mrr - (1.0 + 1.0 / 3) / 2) < 1e-9


def test_aggregate_empty_is_zero_not_a_crash() -> None:
    agg = aggregate([], ks=[1, 10])
    assert agg.n_queries == 0 and agg.hit_at == {1: 0.0, 10: 0.0} and agg.mrr == 0.0


def test_tokens_are_lowercased_unicode_words() -> None:
    assert tokens("Café, RÉSUMÉ! 42x") == ["café", "résumé", "42x"]
