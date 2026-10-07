# ====== Code Summary ======
# SearchHitMapper — turns the graph's Hits into the client SearchHitModels for the two chunk-listing
# routes (search and browse): the flat hit shape (SearchHelpers.to_hit_model), then the request's
# return_fields projection (unrequested keys left UNSET, so response_model_exclude_unset drops them),
# then — only on a debug search — the fusion_score / rerank_score provenance. A field that was never
# set never reaches the wire, so the default (no projection, no debug) output is unchanged.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.public_models.search import Hit

# ====== Local Project Imports ======
from ...libs.search import HitProjection
from .helpers import SearchHelpers
from .models import SearchHitModel

# The debug-only hit fields — never projectable through return_fields, only set by debug=true.
DEBUG_SCORE_FIELDS: frozenset[str] = frozenset({"fusion_score", "rerank_score"})


class SearchHitMapper:
    """Static mapping of graph Hits to projected (and optionally debug-annotated) client hits."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SearchHitMapper is a static-only class and cannot be instantiated.")

    @staticmethod
    def __debug_scores(hit: Hit) -> dict[str, Any]:
        """The score provenance of one hit (rerank_score only when it was reranked)."""
        # 1. fusion_score always (it IS the score when nothing reranked); rerank_score when set.
        scores: dict[str, Any] = {
            "fusion_score": hit.fusion_score if hit.fusion_score is not None else hit.score
        }
        if hit.rerank_score is not None:
            scores["rerank_score"] = hit.rerank_score
        return scores

    @staticmethod
    def projectable_fields(excluded: frozenset[str] = frozenset()) -> list[str]:
        """
        The hit field names a request may name in return_fields.

        Args:
            excluded (frozenset[str]): Extra names the calling route does not serve.

        Returns:
            list[str]: The sorted SearchHitModel fields, minus the debug-only ones and ``excluded``.
        """
        # 1. Debug scores are switched on by debug=true, never selected field by field.
        return sorted(set(SearchHitModel.model_fields) - DEBUG_SCORE_FIELDS - excluded)

    @classmethod
    def map(
        cls, hits: list[Hit], projection: HitProjection | None, debug: bool = False
    ) -> list[SearchHitModel]:
        """
        Map graph hits to client hits, projected and optionally debug-annotated.

        Args:
            hits (list[Hit]): The graph's hits, in delivered order.
            projection (HitProjection | None): The requested fields; None = the full hit.
            debug (bool): Add fusion_score (and rerank_score when reranked) to each hit.

        Returns:
            list[SearchHitModel]: The client hits; only set fields serialize under exclude_unset.
        """
        # 1. The full hit (every field set explicitly), then the projection (only requested set).
        mapped: list[SearchHitModel] = []
        for hit in hits:
            model = SearchHelpers.to_hit_model(hit)
            if projection is not None:
                model = SearchHitModel.model_validate(projection.apply(model.model_dump()))
            # 2. Debug scores join the already-set keys (exclude_unset keeps the projection intact).
            if debug:
                model = SearchHitModel.model_validate(
                    {**model.model_dump(exclude_unset=True), **cls.__debug_scores(hit)}
                )
            mapped.append(model)
        return mapped


__all__ = ["SearchHitMapper", "DEBUG_SCORE_FIELDS"]
