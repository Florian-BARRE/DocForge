# ====== Code Summary ======
# DocumentHitGrouper — the request-edge "group by document" cap on a search result. The search graph
# stays pure and unaware of it: the service asks the graph for a DEEPER page (fetch_depth), then this
# caps the FINAL ranking (after fusion and any rerank) so no document contributes more than
# max_per_document hits, keeping the ranking order and filling up to the caller's limit with the next
# best hits of other documents. When the deeper page holds too few distinct documents, fewer hits
# come back — never more than the cap per document.

# ====== Internal Project Imports ======
from shared_libs.public_models.search import Hit, SearchResult

# The over-fetch multiplier floor — even a 1-per-document cap reads 3x the page to find other docs.
_MIN_FETCH_MULTIPLIER = 3

# Upper bound on the graph page an over-fetch may ask for: it bounds the hydration (and, with a
# rerank stage, the cross-encoder pool, which judges at least the page size) of one request.
MAX_FETCH_DEPTH = 200


class DocumentHitGrouper:
    """Static helpers capping a search result's hits per source document."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("DocumentHitGrouper is a static-only class and cannot be instantiated.")

    @staticmethod
    def fetch_depth(limit: int, max_per_document: int) -> int:
        """
        The graph page size to request so the capped result can still fill ``limit``.

        Args:
            limit (int): The caller's requested hit count.
            max_per_document (int): The per-document cap.

        Returns:
            int: ``limit * max(3, 2 * max_per_document)`` bounded by MAX_FETCH_DEPTH (never below
            ``limit``).
        """
        # 1. Over-fetch proportionally to how aggressively the cap prunes, within a fixed bound.
        wanted = limit * max(_MIN_FETCH_MULTIPLIER, 2 * max_per_document)
        return max(limit, min(wanted, MAX_FETCH_DEPTH))

    @staticmethod
    def cap(hits: list[Hit], limit: int, max_per_document: int) -> list[Hit]:
        """
        Keep at most ``max_per_document`` hits per document, in ranking order, up to ``limit``.

        Args:
            hits (list[Hit]): The final ranked hits, best first.
            limit (int): The caller's requested hit count.
            max_per_document (int): The per-document cap.

        Returns:
            list[Hit]: The capped hits, best first, re-ranked 1..n (may be fewer than ``limit``).
        """
        # 1. Walk the ranking once, admitting a hit only while its document is under the cap.
        per_document: dict[str, int] = {}
        kept: list[Hit] = []
        for hit in hits:
            if len(kept) >= limit:
                break
            seen = per_document.get(hit.document_id, 0)
            if seen >= max_per_document:
                continue
            per_document[hit.document_id] = seen + 1
            kept.append(hit)

        # 2. Re-number the delivered ranks so they stay contiguous after the pruning.
        return [hit.model_copy(update={"rank": rank}) for rank, hit in enumerate(kept, start=1)]

    @classmethod
    def apply(cls, result: SearchResult, limit: int, max_per_document: int) -> SearchResult:
        """
        Cap a search result per document and record the grouping on its debug bag.

        Args:
            result (SearchResult): The over-fetched result (final ranking, best first).
            limit (int): The caller's requested hit count.
            max_per_document (int): The per-document cap.

        Returns:
            SearchResult: The same result with capped hits; ``debug.hit_count`` is the delivered
            count and ``debug.grouping`` says how many hits were fetched before the cap.
        """
        # 1. Cap the hits, then make the debug bag describe what is actually delivered.
        hits = cls.cap(result.hits, limit, max_per_document)
        debug = dict(result.debug or {})
        debug["hit_count"] = len(hits)
        debug["grouping"] = {
            "by": "document",
            "max_per_document": max_per_document,
            "fetched": len(result.hits),
        }
        return result.model_copy(update={"hits": hits, "debug": debug})


__all__ = ["DocumentHitGrouper", "MAX_FETCH_DEPTH"]
