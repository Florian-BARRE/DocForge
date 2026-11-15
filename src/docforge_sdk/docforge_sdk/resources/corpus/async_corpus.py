# ====== Code Summary ======
# The asynchronous document-grid query + bulk delete/enable/reingest resource: the awaiting shell
# over the shared ``_CorpusSpecs`` builders.

# ====== Local Project Imports ======
from ...models.corpus import (
    BulkDeleteResponse,
    BulkEnabledResponse,
    BulkReingestResponse,
    DocumentQueryRequest,
    DocumentQueryResponse,
    DocumentSelector,
)
from .._base import AsyncResource
from .specs import _CorpusSpecs


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
        self,
        collection_id: str,
        selector: DocumentSelector,
        force: bool = False,
        replay_from: str | None = None,
        confirm_estimate: bool = False,
    ) -> BulkReingestResponse:
        """
        Re-run ingestion over every document the selector resolves to (capped fan-out).

        Args:
            collection_id (str): The target collection.
            selector (DocumentSelector): The documents to re-run.
            force (bool): Bypass the stage cache.
            replay_from (str | None): Replay from this post-IR stage on the persisted IR (no
                re-parse); 422 lists the stages the pipeline allows.
            confirm_estimate (bool): Acknowledge the estimate of a reingest above the server's
                threshold (otherwise 409 ``estimate_required`` with the estimate summary).

        Returns:
            BulkReingestResponse: matched / enqueued / capped / skips + one handle per job (429
                ``queue_saturated`` with Retry-After when the queue is full).
        """
        return await self._transport.request(
            self._bulk_reingest_spec(collection_id, selector, force, replay_from, confirm_estimate),
            BulkReingestResponse,
        )
