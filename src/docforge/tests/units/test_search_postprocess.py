# ====== Code Summary ======
# Unit tests for SearchPostProcessor: document grouping and MMR diversity re-ranking
# (the client-side equivalents of Qdrant query_points_groups and MMR).

from backend.libs.search.hybrid.models import SearchResult
from backend.libs.search.pipeline.post import SearchPostProcessor


def _sr(chunk_id: str, document_id: str, score: float) -> SearchResult:
    """Minimal SearchResult for post-processing tests."""
    return SearchResult(
        chunk_id=chunk_id, document_id=document_id, score=score,
        raw_text="text", strategy="recursive", token_count=1,
    )


# ── Grouping ────────────────────────────────────────────────────────────────────


class TestGroupByDocument:
    """group_by_document collapses ranked chunks into document-level groups."""

    def test_orders_groups_by_best_chunk(self) -> None:
        results = [_sr("c1", "dA", 0.9), _sr("c2", "dB", 0.8), _sr("c3", "dA", 0.4)]
        groups = SearchPostProcessor.group_by_document(results, group_size=5, max_groups=10)
        assert [g.document_id for g in groups] == ["dA", "dB"]
        assert groups[0].score == 0.9

    def test_caps_chunks_per_group(self) -> None:
        results = [_sr("c1", "dA", 0.9), _sr("c2", "dA", 0.5), _sr("c3", "dA", 0.3)]
        groups = SearchPostProcessor.group_by_document(results, group_size=2, max_groups=10)
        assert len(groups) == 1
        assert [c.chunk_id for c in groups[0].chunks] == ["c1", "c2"]

    def test_limits_number_of_groups(self) -> None:
        results = [_sr("c1", "dA", 0.9), _sr("c2", "dB", 0.8), _sr("c3", "dC", 0.7)]
        groups = SearchPostProcessor.group_by_document(results, group_size=3, max_groups=2)
        assert [g.document_id for g in groups] == ["dA", "dB"]

    def test_empty_input(self) -> None:
        assert SearchPostProcessor.group_by_document([], group_size=3, max_groups=5) == []


# ── MMR ─────────────────────────────────────────────────────────────────────────


class TestMmrReorder:
    """mmr_reorder balances relevance against diversity over candidate vectors."""

    def test_pure_relevance_keeps_score_order(self) -> None:
        qv = [1.0, 0.0]
        items = [
            (_sr("a", "d", 0.9), [1.0, 0.0]),
            (_sr("b", "d", 0.8), [0.99, 0.01]),
            (_sr("c", "d", 0.7), [0.0, 1.0]),
        ]
        # diversity=0 → λ=1 → pure relevance to the query vector
        order = [r.chunk_id for r in SearchPostProcessor.mmr_reorder(qv, items, diversity=0.0, limit=3)]
        assert order[0] == "a"

    def test_high_diversity_prefers_distinct_vector(self) -> None:
        qv = [1.0, 0.0]
        items = [
            (_sr("a", "d", 0.9), [1.0, 0.0]),
            (_sr("b", "d", 0.85), [0.99, 0.01]),  # near-duplicate of a
            (_sr("c", "d", 0.7), [0.0, 1.0]),     # orthogonal → diverse
        ]
        order = [r.chunk_id for r in SearchPostProcessor.mmr_reorder(qv, items, diversity=0.9, limit=3)]
        assert order[0] == "a"
        assert order[1] == "c"  # diversity beats the near-duplicate b

    def test_limit_truncates(self) -> None:
        qv = [1.0, 0.0]
        items = [(_sr(c, "d", 0.5), [1.0, 0.0]) for c in ("a", "b", "c")]
        assert len(SearchPostProcessor.mmr_reorder(qv, items, diversity=0.5, limit=2)) == 2

    def test_vectorless_candidates_degrade_gracefully(self) -> None:
        qv = [1.0, 0.0]
        items = [(_sr("a", "d", 0.9), []), (_sr("b", "d", 0.8), [])]
        order = [r.chunk_id for r in SearchPostProcessor.mmr_reorder(qv, items, diversity=0.5, limit=5)]
        assert order == ["a", "b"]  # no vectors → original relevance order preserved
