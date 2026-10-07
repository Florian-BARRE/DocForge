# ====== Code Summary ======
# SearchResultFinalizer — composes the request-edge reshapes of a search's FINAL ranking into the one
# ``finalize`` callable the SearchRunner applies before it records the per-search metrics: first the
# min_score cut (drop the hits scoring below the threshold), THEN the per-document cap
# (DocumentHitGrouper) — so a grouped page is filled from hits that passed the threshold. The pure
# graph never sees either. None when the request asked for neither (the untouched default path).

# ====== Standard Library Imports ======
from collections.abc import Callable

# ====== Internal Project Imports ======
from shared_libs.public_models.search import SearchResult

# ====== Local Project Imports ======
from .document_grouping import DocumentHitGrouper


class SearchResultFinalizer:
    """Static builder of the composed min_score → group-by-document finalize step."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SearchResultFinalizer is a static-only class and cannot be instantiated.")

    @staticmethod
    def apply_min_score(result: SearchResult, min_score: float) -> SearchResult:
        """
        Drop the hits whose final score is below ``min_score`` and record it on the debug bag.

        Args:
            result (SearchResult): The final ranking, best first.
            min_score (float): The inclusive lower bound on a kept hit's score.

        Returns:
            SearchResult: The kept hits (order and ranks unchanged — only the tail is cut);
            ``debug.hit_count`` is the kept count and ``debug.min_score`` says how many were dropped.
        """
        # 1. Keep the hits at/above the threshold, then make the debug bag describe the delivery.
        hits = [hit for hit in result.hits if hit.score >= min_score]
        debug = dict(result.debug or {})
        debug["hit_count"] = len(hits)
        dropped = [hit.score for hit in result.hits if hit.score < min_score]
        debug["min_score"] = {
            "threshold": min_score,
            "dropped": len(dropped),
            # The best score that was cut — lets a caller see how far off the threshold is.
            "top_dropped_score": max(dropped) if dropped else None,
        }
        return result.model_copy(update={"hits": hits, "debug": debug})

    @classmethod
    def build(
        cls, top_k: int, max_per_document: int | None, min_score: float | None
    ) -> Callable[[SearchResult], SearchResult] | None:
        """
        Build the composed finalize step for one request.

        Args:
            top_k (int): The caller's requested hit count (the grouping fills up to it).
            max_per_document (int | None): The per-document cap; None = no grouping.
            min_score (float | None): The score threshold; None = no threshold.

        Returns:
            Callable[[SearchResult], SearchResult] | None: min_score then grouping, or None when
            the request asked for neither.
        """
        # 1. Nothing to reshape → no finalize at all (the default path stays byte-identical).
        if max_per_document is None and min_score is None:
            return None

        # 2. Threshold first, then the per-document cap over what survived it.
        def finalize(result: SearchResult) -> SearchResult:
            if min_score is not None:
                result = cls.apply_min_score(result, min_score)
            if max_per_document is not None:
                result = DocumentHitGrouper.apply(result, top_k, max_per_document)
            return result

        return finalize


__all__ = ["SearchResultFinalizer"]
