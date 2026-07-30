# ====== Code Summary ======
# The search resource — a hybrid search over one collection's chunks. All URL/body logic lives once in
# the pure _SearchSpecs mixin so AsyncSearch and SyncSearch differ ONLY by ``await``.

# ====== Local Project Imports ======
from .._requestspec import RequestSpec
from ..models.search import SearchRequest, SearchResponse
from ._base import AsyncResource, SyncResource, _ResourceMixin


class _SearchSpecs(_ResourceMixin):
    """Pure ``RequestSpec`` builders for the search endpoint — the single source of URL/body logic."""

    _COLLECTIONS_PATH = "/collections"

    def _search_spec(self, collection_id: str, request: SearchRequest) -> RequestSpec:
        """
        Build the spec for searching a collection.

        Args:
            collection_id (str): The collection to search.
            request (SearchRequest): The query, filters and target modalities.

        Returns:
            RequestSpec: A POST to the collection's ``/search`` route carrying the query body.
        """
        return RequestSpec(
            "POST",
            f"{self._COLLECTIONS_PATH}/{collection_id}/search",
            json=request.model_dump(mode="json"),
        )


class AsyncSearch(AsyncResource, _SearchSpecs):
    """Asynchronous hybrid search."""

    async def search(self, collection_id: str, request: SearchRequest) -> SearchResponse:
        """
        Run a hybrid search over a collection and return ranked, hydrated chunk hits.

        Args:
            collection_id (str): The collection to search.
            request (SearchRequest): The query, filters and target modalities.

        Returns:
            SearchResponse: The echoed query and its hits, best first.
        """
        return await self._transport.request(
            self._search_spec(collection_id, request), SearchResponse
        )


class SyncSearch(SyncResource, _SearchSpecs):
    """Synchronous hybrid search."""

    def search(self, collection_id: str, request: SearchRequest) -> SearchResponse:
        """
        Run a hybrid search over a collection and return ranked, hydrated chunk hits.

        Args:
            collection_id (str): The collection to search.
            request (SearchRequest): The query, filters and target modalities.

        Returns:
            SearchResponse: The echoed query and its hits, best first.
        """
        return self._transport.request(self._search_spec(collection_id, request), SearchResponse)


__all__ = ["AsyncSearch", "SyncSearch"]
