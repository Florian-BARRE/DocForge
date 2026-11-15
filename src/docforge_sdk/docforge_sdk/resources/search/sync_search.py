# ====== Code Summary ======
# GENERATED FILE — DO NOT EDIT. Derived from async_search.py by scripts/generate_sync.py;
# regenerate with `uv run --frozen python scripts/generate_sync.py` from src/docforge_sdk
# (tests/unit/test_sync_codegen.py fails when this file drifts from its async source).
# The synchronous hybrid search resource: the blocking shell over the shared ``_SearchSpecs``
# builders.

# ====== Local Project Imports ======
from ...models.search import (
    ChunkBrowseRequest,
    ChunkBrowseResponse,
    SearchHealthSummary,
    SearchRequest,
    SearchResponse,
)
from .._base import SyncResource
from .specs import _SearchSpecs


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

    def browse(self, collection_id: str, request: ChunkBrowseRequest) -> ChunkBrowseResponse:
        """
        List a collection's chunks matching a filter, in reading order, without a query.

        Args:
            collection_id (str): The collection to browse.
            request (ChunkBrowseRequest): Filters, page size, cursor and optional return_fields.

        Returns:
            ChunkBrowseResponse: One page, the next page's cursor (None on the last) and any hints.
        """
        return self._transport.request(
            self._browse_spec(collection_id, request), ChunkBrowseResponse
        )

    def get_search_health(self) -> SearchHealthSummary:
        """
        Fetch the deployment-wide search-runtime health summary (the cockpit tile).

        Returns:
            SearchHealthSummary: Cumulative-since-start totals, rates and p95 latency.
        """
        return self._transport.request(self._search_health_spec(), SearchHealthSummary)
