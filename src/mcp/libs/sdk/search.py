# ====== Code Summary ======
# Search sub-API: hybrid retrieval over one collection, under
# POST /api/v1/collections/{collection_id}/search.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .transport import DocForgeTransport


class SearchApi(LoggerClass):
    """Hybrid search endpoint (dense + sparse fusion, optional ColBERT late-interaction rescore)."""

    def __init__(self, transport: DocForgeTransport) -> None:
        """
        Bind the shared transport.

        Args:
            transport (DocForgeTransport): The shared HTTP transport.
        """
        LoggerClass.__init__(self)
        self._t = transport

    async def search(
        self,
        collection_id: str,
        query: str,
        limit: int = 10,
        filters: dict[str, Any] | None = None,
        search_in: list[dict[str, Any]] | None = None,
        use_late_interaction: bool | None = None,
        rescore_pool_size: int | None = None,
    ) -> Any:
        """
        Run a hybrid search over a collection and return ranked, hydrated chunk hits.

        Args:
            collection_id (str): Target collection UUID.
            query (str): The natural-language query.
            limit (int): Number of fused results (1-100).
            filters (dict | None): Exact/any-of constraints on FILTERABLE fields (a scalar is
                an equality match, a list is a set-membership match).
            search_in (list[dict] | None): Targets [{"field", "semantic", "lexical"}]; None
                searches the chunk body ("content") on both axes.
            use_late_interaction (bool | None): Opt into the ColBERT re-score for this query.
            rescore_pool_size (int | None): Fused candidate pool size ColBERT re-scores.

        Returns:
            Any: SearchResponse — query, hits, debug_info.
        """
        # 1. Only send the knobs the caller actually set; the request model defaults the rest
        body: dict[str, Any] = {"query": query, "limit": limit}
        if filters is not None:
            body["filters"] = filters
        if search_in is not None:
            body["search_in"] = search_in
        if use_late_interaction is not None:
            body["use_late_interaction"] = use_late_interaction
        if rescore_pool_size is not None:
            body["rescore_pool_size"] = rescore_pool_size
        return await self._t.post(f"/collections/{collection_id}/search", body)
