# ====== Code Summary ======
# The asynchronous hybrid search resource: the awaiting shell over the shared ``_SearchSpecs``
# builders.

# ====== Local Project Imports ======
from ...models.search import (
    ChunkBrowseRequest,
    ChunkBrowseResponse,
    SearchHealthSummary,
    SearchRequest,
    SearchResponse,
)
from .._base import AsyncResource
from .specs import _SearchSpecs


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

    async def browse(self, collection_id: str, request: ChunkBrowseRequest) -> ChunkBrowseResponse:
        """
        List a collection's chunks matching a filter, in reading order, without a query.

        Args:
            collection_id (str): The collection to browse.
            request (ChunkBrowseRequest): Filters, page size, cursor and optional return_fields.

        Returns:
            ChunkBrowseResponse: One page, the next page's cursor (None on the last) and any hints.
        """
        return await self._transport.request(
            self._browse_spec(collection_id, request), ChunkBrowseResponse
        )

    async def get_search_health(self) -> SearchHealthSummary:
        """
        Fetch the deployment-wide search-runtime health summary (the cockpit tile).

        Returns:
            SearchHealthSummary: Cumulative-since-start totals, rates and p95 latency.
        """
        return await self._transport.request(self._search_health_spec(), SearchHealthSummary)
