# ====== Code Summary ======
# The corpus resource — the server-side document GRID and its bulk operations. `query` returns one
# filtered/sorted/paginated page of a collection's documents; the three bulk ops (`bulk_delete`,
# `bulk_set_enabled`, `bulk_reingest`) each take the ONE shared DocumentSelector (an explicit id set
# XOR a filter minus a few deselected ids), so "act on all 100k matching, minus 3" needs no client-side
# id enumeration. All URL/body logic lives once in the pure _CorpusSpecs mixin; the async/sync shells
# differ only by ``await``.

# ====== Local Project Imports ======
from .._requestspec import RequestSpec
from ..models.corpus import (
    BulkDeleteResponse,
    BulkEnabledResponse,
    BulkReingestResponse,
    DocumentQueryRequest,
    DocumentQueryResponse,
    DocumentSelector,
)
from ._base import AsyncResource, SyncResource, _ResourceMixin


class _CorpusSpecs(_ResourceMixin):
    """Pure ``RequestSpec`` builders for the corpus grid + bulk-op endpoints."""

    _COLLECTIONS_PATH = "/collections"

    def _docs_path(self, collection_id: str, action: str) -> str:
        """The path to a collection's documents sub-action (query / delete / set-enabled / reingest)."""
        return f"{self._COLLECTIONS_PATH}/{collection_id}/documents/{action}"

    def _query_spec(self, collection_id: str, request: DocumentQueryRequest) -> RequestSpec:
        """A POST carrying the filter/sort/pagination body → one page of grid rows."""
        return RequestSpec(
            "POST", self._docs_path(collection_id, "query"), json=request.model_dump(mode="json")
        )

    def _bulk_delete_spec(self, collection_id: str, selector: DocumentSelector) -> RequestSpec:
        """A POST carrying the selector → a bulk delete."""
        return RequestSpec(
            "POST", self._docs_path(collection_id, "delete"), json=selector.model_dump(mode="json")
        )

    def _bulk_set_enabled_spec(
        self, collection_id: str, selector: DocumentSelector, enabled: bool
    ) -> RequestSpec:
        """A POST carrying the selector (+ ``enabled`` query param) → a bulk enable/disable."""
        return RequestSpec(
            "POST",
            self._docs_path(collection_id, "set-enabled"),
            params={"enabled": enabled},
            json=selector.model_dump(mode="json"),
        )

    def _bulk_reingest_spec(
        self, collection_id: str, selector: DocumentSelector, force: bool
    ) -> RequestSpec:
        """A POST carrying the selector (+ ``force`` query param) → a bulk re-ingest fan-out."""
        return RequestSpec(
            "POST",
            self._docs_path(collection_id, "reingest"),
            params={"force": force},
            json=selector.model_dump(mode="json"),
        )


class AsyncCorpus(AsyncResource, _CorpusSpecs):
    """Asynchronous document-grid query + bulk delete/enable/reingest."""

    async def query(
        self, collection_id: str, request: DocumentQueryRequest | None = None
    ) -> DocumentQueryResponse:
        """
        Return one filtered, sorted, paginated page of a collection's documents + the total count.

        Args:
            collection_id (str): The collection to query.
            request (DocumentQueryRequest | None): Filter/sort/pagination; omitted → the first page.

        Returns:
            DocumentQueryResponse: total + limit/offset echo + the page of grid rows.
        """
        return await self._transport.request(
            self._query_spec(collection_id, request or DocumentQueryRequest()),
            DocumentQueryResponse,
        )

    async def bulk_delete(
        self, collection_id: str, selector: DocumentSelector
    ) -> BulkDeleteResponse:
        """Delete every document the selector resolves to (id set XOR filter-minus-excludes)."""
        return await self._transport.request(
            self._bulk_delete_spec(collection_id, selector), BulkDeleteResponse
        )

    async def bulk_set_enabled(
        self, collection_id: str, selector: DocumentSelector, enabled: bool
    ) -> BulkEnabledResponse:
        """Enable/disable (searchability) every document the selector resolves to."""
        return await self._transport.request(
            self._bulk_set_enabled_spec(collection_id, selector, enabled), BulkEnabledResponse
        )

    async def bulk_reingest(
        self, collection_id: str, selector: DocumentSelector, force: bool = False
    ) -> BulkReingestResponse:
        """Re-run the full ingestion over every document the selector resolves to (capped fan-out)."""
        return await self._transport.request(
            self._bulk_reingest_spec(collection_id, selector, force), BulkReingestResponse
        )


class SyncCorpus(SyncResource, _CorpusSpecs):
    """Synchronous document-grid query + bulk delete/enable/reingest."""

    def query(
        self, collection_id: str, request: DocumentQueryRequest | None = None
    ) -> DocumentQueryResponse:
        """Return one filtered/sorted/paginated page of a collection's documents + the total count."""
        return self._transport.request(
            self._query_spec(collection_id, request or DocumentQueryRequest()),
            DocumentQueryResponse,
        )

    def bulk_delete(self, collection_id: str, selector: DocumentSelector) -> BulkDeleteResponse:
        """Delete every document the selector resolves to (id set XOR filter-minus-excludes)."""
        return self._transport.request(
            self._bulk_delete_spec(collection_id, selector), BulkDeleteResponse
        )

    def bulk_set_enabled(
        self, collection_id: str, selector: DocumentSelector, enabled: bool
    ) -> BulkEnabledResponse:
        """Enable/disable (searchability) every document the selector resolves to."""
        return self._transport.request(
            self._bulk_set_enabled_spec(collection_id, selector, enabled), BulkEnabledResponse
        )

    def bulk_reingest(
        self, collection_id: str, selector: DocumentSelector, force: bool = False
    ) -> BulkReingestResponse:
        """Re-run the full ingestion over every document the selector resolves to (capped fan-out)."""
        return self._transport.request(
            self._bulk_reingest_spec(collection_id, selector, force), BulkReingestResponse
        )


__all__ = ["AsyncCorpus", "SyncCorpus"]
