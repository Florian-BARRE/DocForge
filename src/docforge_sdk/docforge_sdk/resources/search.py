# ====== Code Summary ======
# The search resource — a hybrid search over one collection's chunks, plus the deployment-wide
# search-health summary tile. All URL/body logic lives once in the pure _SearchSpecs mixin so the
# async/sync shells differ ONLY by ``await``.

# ====== Local Project Imports ======
from .._requestspec import RequestSpec
from ..models.search import SearchHealthSummary, SearchRequest, SearchResponse
from ._base import AsyncResource, SyncResource, _ResourceMixin


class _SearchSpecs(_ResourceMixin):
    """Pure ``RequestSpec`` builders for the search endpoints — the single source of URL/body logic."""

    _COLLECTIONS_PATH = "/collections"
    _SEARCH_HEALTH_PATH = "/search/health"

    def _search_spec(self, collection_id: str, request: SearchRequest) -> RequestSpec:
        """
        Build the spec for searching a collection.

        Args:
            collection_id (str): The collection to search.
            request (SearchRequest): The query, filters, target modalities and the optional
                ``return_fields`` / ``group_by`` / ``max_per_document`` shaping.

        Returns:
            RequestSpec: A POST to the collection's ``/search`` route carrying the query body.
        """
        # 1. Dump the body, sending the response-shaping knobs only when used: a pre-0.24 server's
        #    SearchRequest forbids unknown keys (even a null return_fields/group_by would 422 every
        #    plain search), and the backend 422s a max_per_document sent without group_by — so the
        #    untouched default (1) is dropped unless grouping is on or the caller set it explicitly.
        body = request.model_dump(mode="json")
        for knob in ("return_fields", "group_by"):
            if body.get(knob) is None:
                body.pop(knob, None)
        if request.group_by is None and "max_per_document" not in request.model_fields_set:
            body.pop("max_per_document")
        return RequestSpec("POST", f"{self._COLLECTIONS_PATH}/{collection_id}/search", json=body)

    def _search_health_spec(self) -> RequestSpec:
        """
        Build the spec for the deployment-wide search-health summary.

        Returns:
            RequestSpec: A GET on the process-global ``/search/health`` tile route.
        """
        return RequestSpec("GET", self._SEARCH_HEALTH_PATH)


class AsyncSearch(AsyncResource, _SearchSpecs):
    """Asynchronous hybrid search."""

    async def search(self, collection_id: str, request: SearchRequest) -> SearchResponse:
        """
        Run a hybrid search over a collection and return ranked, hydrated chunk hits.

        Args:
            collection_id (str): The collection to search.
            request (SearchRequest): The query, filters, target modalities and the optional
                ``return_fields`` / ``group_by`` / ``max_per_document`` shaping.

        Returns:
            SearchResponse: The echoed query and its hits, best first.
        """
        return await self._transport.request(
            self._search_spec(collection_id, request), SearchResponse
        )

    async def get_search_health(self) -> SearchHealthSummary:
        """
        Fetch the deployment-wide search-runtime health summary (the cockpit tile).

        Returns:
            SearchHealthSummary: Cumulative-since-start totals, rates and p95 latency.
        """
        return await self._transport.request(self._search_health_spec(), SearchHealthSummary)


class SyncSearch(SyncResource, _SearchSpecs):
    """Synchronous hybrid search."""

    def search(self, collection_id: str, request: SearchRequest) -> SearchResponse:
        """
        Run a hybrid search over a collection and return ranked, hydrated chunk hits.

        Args:
            collection_id (str): The collection to search.
            request (SearchRequest): The query, filters, target modalities and the optional
                ``return_fields`` / ``group_by`` / ``max_per_document`` shaping.

        Returns:
            SearchResponse: The echoed query and its hits, best first.
        """
        return self._transport.request(self._search_spec(collection_id, request), SearchResponse)

    def get_search_health(self) -> SearchHealthSummary:
        """
        Fetch the deployment-wide search-runtime health summary (the cockpit tile).

        Returns:
            SearchHealthSummary: Cumulative-since-start totals, rates and p95 latency.
        """
        return self._transport.request(self._search_health_spec(), SearchHealthSummary)


__all__ = ["AsyncSearch", "SyncSearch"]
