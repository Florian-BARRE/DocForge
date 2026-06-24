# ====== Code Summary ======
# Search sub-API: collection-wide and per-document hybrid retrieval under
# /api/v1/collections/{collection_id}/documents (.../search and .../{document_id}/search).

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .transport import DocForgeTransport


class SearchApi(LoggerClass):
    """Hybrid search endpoints (dense + sparse fusion, optional query transform + rerank)."""

    def __init__(self, transport: DocForgeTransport) -> None:
        """Bind the shared transport.

        Args:
            transport (DocForgeTransport): The shared HTTP transport.
        """
        LoggerClass.__init__(self)
        self._t = transport

    async def collection(
        self,
        collection_id: str,
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        weights: dict[str, float] | None = None,
        debug: bool = False,
    ) -> Any:
        """
        Hybrid search over a whole collection.

        Args:
            collection_id (str): Target collection UUID.
            query (str): Natural-language query.
            top_k (int): Max results (1–100).
            filters (dict | None): Qdrant payload filter (e.g. {"must": [{"key": ..., "match": ...}]}).
            weights (dict | None): Per-vector fusion weight overrides (e.g. {"dense-text": 0.7}).
            debug (bool): Include per-vector rank breakdown in each result.

        Returns:
            Any: Ranked chunk results (+ groups/debug_info when applicable).
        """
        return await self._t.post(
            f"/collections/{collection_id}/documents/search",
            self._body(query, top_k, filters, weights, debug),
        )

    async def within_document(
        self,
        collection_id: str,
        document_id: str,
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        weights: dict[str, float] | None = None,
        debug: bool = False,
    ) -> Any:
        """
        Hybrid search restricted to a single document's chunks.

        Args:
            collection_id (str): Target collection UUID.
            document_id (str): Document UUID the search is pinned to.
            query (str): Natural-language query.
            top_k (int): Max results (1–100).
            filters (dict | None): Additional Qdrant payload filter.
            weights (dict | None): Per-vector fusion weight overrides.
            debug (bool): Include per-vector rank breakdown.

        Returns:
            Any: Ranked chunk results within the document.
        """
        return await self._t.post(
            f"/collections/{collection_id}/documents/{document_id}/search",
            self._body(query, top_k, filters, weights, debug),
        )

    @staticmethod
    def _body(
        query: str,
        top_k: int,
        filters: dict[str, Any] | None,
        weights: dict[str, float] | None,
        debug: bool,
    ) -> dict[str, Any]:
        """Assemble the SearchRequest body (None filters/weights are omitted)."""
        body: dict[str, Any] = {"query": query, "top_k": top_k, "debug": debug}
        if filters is not None:
            body["filters"] = filters
        if weights is not None:
            body["weights"] = weights
        return body
