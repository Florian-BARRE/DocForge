# ====== Code Summary ======
# SearchPostProcessor — pure post-retrieval transforms applied by the search engine
# after fusion + hydration (+ optional rerank):
#   - group_by_document: collapse the flat chunk list into document-level groups
#       (Qdrant query_points_groups equivalent, done client-side to compose with the
#        multi-field weighted fusion).
#   - mmr_reorder: Maximal Marginal Relevance diversity re-ranking over candidate
#       dense vectors (Qdrant MMR equivalent, client-side).
# No I/O — fully unit-testable.

# ====== Standard Library Imports ======
from __future__ import annotations

import math

# ====== Local Project Imports ======
from libs.search.hybrid.models import DocumentGroup, SearchResult


class SearchPostProcessor:
    """
    Static, side-effect-free post-processing of fused search results.

    Both transforms operate on already-hydrated ``SearchResult`` objects so they
    compose with any fusion method / vector mode.  The engine calls them after
    retrieval (and after rerank, when enabled).
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        raise TypeError("SearchPostProcessor is a static-only class and cannot be instantiated.")

    @staticmethod
    def group_by_document(
        results: list[SearchResult],
        group_size: int,
        max_groups: int,
    ) -> list[DocumentGroup]:
        """
        Collapse a ranked chunk list into document-level groups.

        Groups are ordered by their best (first-seen, i.e. highest-ranked) chunk; each
        group keeps at most ``group_size`` chunks in rank order; at most ``max_groups``
        groups are returned.

        Args:
            results (list[SearchResult]): Ranked chunks, best-first.
            group_size (int): Max chunks kept per document.
            max_groups (int): Max number of document groups returned.

        Returns:
            list[DocumentGroup]: Document groups in descending relevance order.
        """
        groups: dict[str, DocumentGroup] = {}
        # 1. Walk results in rank order; first hit of a document fixes its group score
        for r in results:
            grp = groups.get(r.document_id)
            if grp is None:
                grp = DocumentGroup(document_id=r.document_id, score=r.score, chunks=[])
                groups[r.document_id] = grp
            if len(grp.chunks) < group_size:
                grp.chunks.append(r)
        # 2. Insertion order already reflects descending relevance (results were sorted)
        return list(groups.values())[:max_groups]

    @staticmethod
    def mmr_reorder(
        query_vector: list[float],
        items: list[tuple[SearchResult, list[float]]],
        diversity: float,
        limit: int,
    ) -> list[SearchResult]:
        """
        Re-rank candidates with Maximal Marginal Relevance (MMR).

        Greedy selection maximizing ``λ·rel(c) − (1−λ)·max_{s∈selected} sim(c, s)`` where
        ``λ = 1 − diversity`` (diversity=0 → pure relevance, 1 → pure diversity), ``rel`` is
        cosine similarity to the query, and ``sim`` is cosine similarity between candidates.

        Items lacking a usable vector keep their original relevance order and are appended
        after the MMR-selected ones (graceful degradation for dense-less providers).

        Args:
            query_vector (list[float]): The query's dense embedding.
            items (list[tuple[SearchResult, list[float]]]): Candidates paired with their
                dense vectors (empty vector → no diversity signal for that item).
            diversity (float): 0.0 (pure relevance) … 1.0 (pure diversity).
            limit (int): Number of results to return.

        Returns:
            list[SearchResult]: Re-ordered results, length ``min(limit, len(items))``.
        """
        # 1. Split candidates with usable vectors from those without
        usable = [(r, v) for r, v in items if v]
        vectorless = [r for r, v in items if not v]
        if not usable:
            return [r for r, _ in items][:limit]

        lam = max(0.0, min(1.0, 1.0 - diversity))
        # 2. Precompute query-relevance per candidate (cosine to the query vector)
        rel = {id(r): SearchPostProcessor._cosine(query_vector, v) for r, v in usable}

        selected: list[SearchResult] = []
        selected_vecs: list[list[float]] = []
        pool = list(usable)
        # 3. Greedy MMR selection
        while pool and len(selected) < limit:
            best_idx, best_score = 0, -math.inf
            for i, (r, v) in enumerate(pool):
                penalty = max(
                    (SearchPostProcessor._cosine(v, sv) for sv in selected_vecs),
                    default=0.0,
                )
                mmr = lam * rel[id(r)] - (1.0 - lam) * penalty
                if mmr > best_score:
                    best_idx, best_score = i, mmr
            r, v = pool.pop(best_idx)
            selected.append(r)
            selected_vecs.append(v)

        # 4. Append vectorless candidates (already relevance-ordered) to fill the limit
        return (selected + vectorless)[:limit]

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        """
        Cosine similarity between two equal-length vectors.

        Args:
            a (list[float]): First vector.
            b (list[float]): Second vector.

        Returns:
            float: Cosine similarity in [-1, 1]; 0.0 when either norm is zero or lengths differ.
        """
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0.0 or nb == 0.0:
            return 0.0
        return dot / (na * nb)
