# ====== Code Summary ======
# The collections resource (CRUD over a collection's full contract). All URL/body logic lives once in
# the pure _CollectionsSpecs mixin, so AsyncCollections and SyncCollections have identical public
# surfaces whose bodies differ ONLY by ``await``.

# ====== Standard Library Imports ======
# `list`/`dict` annotations must stay lazy: a `list(...)` method in this class shadows the builtin in
# the class namespace, so eager annotation evaluation would break `list[str]` param hints (PEP 563).
from __future__ import annotations

from typing import Literal

# ====== Local Project Imports ======
from .._requestspec import RequestSpec
from ..models.collections import (
    BulkReingestAccepted,
    BulkReingestRequest,
    CollectionListItem,
    CollectionModel,
    CreateCollectionRequest,
    UpdateCollectionRequest,
)
from ..models.corpus import DocumentFilter
from ..models.estimate import CollectionEstimateRequest, CostEstimate
from ..models.health import CollectionHealthResponse
from ..models.storage import CollectionStorageResponse
from ._base import AsyncResource, SyncResource, _ResourceMixin


class _CollectionsSpecs(_ResourceMixin):
    """Pure ``RequestSpec`` builders for the collections endpoints — the single source of URL/body logic."""

    _COLLECTIONS_PATH = "/collections"

    def _list_spec(self) -> RequestSpec:
        """
        Build the spec for listing collections.

        Returns:
            RequestSpec: A GET on the collections collection.
        """
        return RequestSpec("GET", self._COLLECTIONS_PATH)

    def _get_spec(self, collection_id: str) -> RequestSpec:
        """
        Build the spec for fetching one collection.

        Args:
            collection_id (str): The collection's UUID.

        Returns:
            RequestSpec: A GET on the collection resource.
        """
        return RequestSpec("GET", f"{self._COLLECTIONS_PATH}/{collection_id}")

    def _create_spec(self, request: CreateCollectionRequest) -> RequestSpec:
        """
        Build the spec for creating a collection.

        Args:
            request (CreateCollectionRequest): The create body (contract + schema + pipeline).

        Returns:
            RequestSpec: A POST to the collections collection carrying the full body.
        """
        return RequestSpec("POST", self._COLLECTIONS_PATH, json=request.model_dump(mode="json"))

    def _update_spec(self, collection_id: str, request: UpdateCollectionRequest) -> RequestSpec:
        """
        Build the spec for patching a collection, sending only the caller-set fields.

        Args:
            collection_id (str): The collection to patch.
            request (UpdateCollectionRequest): The patch body (partial by design).

        Returns:
            RequestSpec: A PATCH on the collection resource with a minimal body.
        """
        return RequestSpec(
            "PATCH",
            f"{self._COLLECTIONS_PATH}/{collection_id}",
            json=request.model_dump(mode="json", exclude_unset=True),
        )

    def _delete_spec(self, collection_id: str) -> RequestSpec:
        """
        Build the spec for deleting a collection.

        Args:
            collection_id (str): The collection to delete.

        Returns:
            RequestSpec: A DELETE on the collection resource.
        """
        return RequestSpec("DELETE", f"{self._COLLECTIONS_PATH}/{collection_id}")

    def _health_spec(self, collection_id: str) -> RequestSpec:
        """
        Build the spec for probing a collection's on-demand operational health.

        Args:
            collection_id (str): The collection's UUID.

        Returns:
            RequestSpec: A GET on the collection's health sub-resource.
        """
        return RequestSpec("GET", f"{self._COLLECTIONS_PATH}/{collection_id}/health")

    def _storage_spec(self, collection_id: str) -> RequestSpec:
        """
        Build the spec for measuring a collection's material storage footprint.

        Args:
            collection_id (str): The collection's UUID.

        Returns:
            RequestSpec: A GET on the collection's storage sub-resource.
        """
        return RequestSpec("GET", f"{self._COLLECTIONS_PATH}/{collection_id}/storage")

    def _reingest_spec(self, collection_id: str, request: BulkReingestRequest) -> RequestSpec:
        """
        Build the spec for re-running the full pipeline over a collection's corpus.

        Args:
            collection_id (str): The collection to re-ingest.
            request (BulkReingestRequest): Whole collection (default) or an explicit subset.

        Returns:
            RequestSpec: A POST on the collection's ``/reingest`` route with the subset body.
        """
        return RequestSpec(
            "POST",
            f"{self._COLLECTIONS_PATH}/{collection_id}/reingest",
            json=request.model_dump(mode="json"),
        )

    def _estimate_spec(self, collection_id: str, request: CollectionEstimateRequest) -> RequestSpec:
        """
        Build the spec for projecting a collection's ingestion cost/volume before spending.

        Args:
            collection_id (str): The collection to estimate over.
            request (CollectionEstimateRequest): The scope, or an explicit document-id/filter subset.

        Returns:
            RequestSpec: A POST on the collection's ``/estimate`` route with the selector body.
        """
        return RequestSpec(
            "POST",
            f"{self._COLLECTIONS_PATH}/{collection_id}/estimate",
            json=request.model_dump(mode="json", exclude_none=True),
        )


class AsyncCollections(AsyncResource, _CollectionsSpecs):
    """Asynchronous collection management (list / get / create / update / delete)."""

    async def list(self) -> list[CollectionListItem]:
        """
        List every collection with its full schema and server-computed health summary.

        Returns:
            list[CollectionListItem]: All contracts (schema included), each with its health summary.
        """
        return await self._transport.request(self._list_spec(), list[CollectionListItem])

    async def get(self, collection_id: str) -> CollectionModel:
        """
        Fetch one collection's full contract.

        Args:
            collection_id (str): The collection's UUID.

        Returns:
            CollectionModel: Identity, limits, schema and config blobs.
        """
        return await self._transport.request(self._get_spec(collection_id), CollectionModel)

    async def create(self, request: CreateCollectionRequest) -> CollectionModel:
        """
        Create a collection from its contract, schema and (optional) pipeline.

        Args:
            request (CreateCollectionRequest): The create body.

        Returns:
            CollectionModel: The created contract.
        """
        return await self._transport.request(self._create_spec(request), CollectionModel)

    async def update(self, collection_id: str, request: UpdateCollectionRequest) -> CollectionModel:
        """
        Patch identity/limits, the metadata schema and/or the config blobs.

        Args:
            collection_id (str): The collection to patch.
            request (UpdateCollectionRequest): The partial patch body.

        Returns:
            CollectionModel: The updated contract.
        """
        return await self._transport.request(
            self._update_spec(collection_id, request), CollectionModel
        )

    async def delete(self, collection_id: str) -> None:
        """
        Delete a collection.

        Args:
            collection_id (str): The collection to delete.
        """
        return await self._transport.request(self._delete_spec(collection_id), type(None))

    async def health(self, collection_id: str) -> CollectionHealthResponse:
        """
        Probe a collection's operational health on demand (no job enqueued, no spend).

        Args:
            collection_id (str): The collection's UUID.

        Returns:
            CollectionHealthResponse: Per-provider reachability, index stats and the rolled-up verdict.
        """
        return await self._transport.request(
            self._health_spec(collection_id), CollectionHealthResponse
        )

    async def storage(self, collection_id: str) -> CollectionStorageResponse:
        """
        Measure a collection's material footprint per store (S3 exact, Postgres/Qdrant estimated).

        Args:
            collection_id (str): The collection's UUID.

        Returns:
            CollectionStorageResponse: Per-store totals + the per-document breakdown, heaviest first.
        """
        return await self._transport.request(
            self._storage_spec(collection_id), CollectionStorageResponse
        )

    async def reingest(
        self, collection_id: str, request: BulkReingestRequest | None = None
    ) -> BulkReingestAccepted:
        """
        Re-run the full pipeline over a collection's corpus — all documents, or an explicit subset.

        A match above the server's per-call fan-out ceiling enqueues only the first N and reports
        ``capped=true`` with the full ``matched`` count. Poll each returned job handle for progress.

        Args:
            collection_id (str): The collection to re-ingest.
            request (BulkReingestRequest | None): The subset to re-run; omit for the whole collection.
                Set ``request.force`` to bypass the stage cache and recompute every stage.

        Returns:
            BulkReingestAccepted: matched / enqueued / capped + one job handle per enqueued run.
        """
        return await self._transport.request(
            self._reingest_spec(collection_id, request or BulkReingestRequest()),
            BulkReingestAccepted,
        )

    async def estimate(
        self,
        collection_id: str,
        scope: Literal["pending", "all"] = "pending",
        document_ids: list[str] | None = None,
        filter: DocumentFilter | None = None,
    ) -> CostEstimate:
        """
        Project a collection's ingestion cost and volume before spending a cent.

        Args:
            collection_id (str): The collection to estimate over.
            scope (str): Whole-collection selector used when neither subset below is given —
                ``pending`` (not-yet-ingested, the default) or ``all`` (every document).
            document_ids (list[str] | None): Estimate over exactly these document ids (mutually
                exclusive with ``filter``; overrides ``scope`` when set).
            filter (DocumentFilter | None): Estimate over the documents matching this corpus filter
                (mutually exclusive with ``document_ids``; overrides ``scope`` when set).

        Returns:
            CostEstimate: The per-stage breakdown, projected volume, totals, assumptions and caveats.
        """
        request = CollectionEstimateRequest(scope=scope, document_ids=document_ids, filter=filter)
        return await self._transport.request(
            self._estimate_spec(collection_id, request), CostEstimate
        )


class SyncCollections(SyncResource, _CollectionsSpecs):
    """Synchronous collection management (list / get / create / update / delete)."""

    def list(self) -> list[CollectionListItem]:
        """
        List every collection with its full schema and server-computed health summary.

        Returns:
            list[CollectionListItem]: All contracts (schema included), each with its health summary.
        """
        return self._transport.request(self._list_spec(), list[CollectionListItem])

    def get(self, collection_id: str) -> CollectionModel:
        """
        Fetch one collection's full contract.

        Args:
            collection_id (str): The collection's UUID.

        Returns:
            CollectionModel: Identity, limits, schema and config blobs.
        """
        return self._transport.request(self._get_spec(collection_id), CollectionModel)

    def create(self, request: CreateCollectionRequest) -> CollectionModel:
        """
        Create a collection from its contract, schema and (optional) pipeline.

        Args:
            request (CreateCollectionRequest): The create body.

        Returns:
            CollectionModel: The created contract.
        """
        return self._transport.request(self._create_spec(request), CollectionModel)

    def update(self, collection_id: str, request: UpdateCollectionRequest) -> CollectionModel:
        """
        Patch identity/limits, the metadata schema and/or the config blobs.

        Args:
            collection_id (str): The collection to patch.
            request (UpdateCollectionRequest): The partial patch body.

        Returns:
            CollectionModel: The updated contract.
        """
        return self._transport.request(self._update_spec(collection_id, request), CollectionModel)

    def delete(self, collection_id: str) -> None:
        """
        Delete a collection.

        Args:
            collection_id (str): The collection to delete.
        """
        return self._transport.request(self._delete_spec(collection_id), type(None))

    def health(self, collection_id: str) -> CollectionHealthResponse:
        """
        Probe a collection's operational health on demand (no job enqueued, no spend).

        Args:
            collection_id (str): The collection's UUID.

        Returns:
            CollectionHealthResponse: Per-provider reachability, index stats and the rolled-up verdict.
        """
        return self._transport.request(self._health_spec(collection_id), CollectionHealthResponse)

    def storage(self, collection_id: str) -> CollectionStorageResponse:
        """
        Measure a collection's material footprint per store (S3 exact, Postgres/Qdrant estimated).

        Args:
            collection_id (str): The collection's UUID.

        Returns:
            CollectionStorageResponse: Per-store totals + the per-document breakdown, heaviest first.
        """
        return self._transport.request(self._storage_spec(collection_id), CollectionStorageResponse)

    def reingest(
        self, collection_id: str, request: BulkReingestRequest | None = None
    ) -> BulkReingestAccepted:
        """
        Re-run the full pipeline over a collection's corpus — all documents, or an explicit subset.

        A match above the server's per-call fan-out ceiling enqueues only the first N and reports
        ``capped=true`` with the full ``matched`` count. Poll each returned job handle for progress.

        Args:
            collection_id (str): The collection to re-ingest.
            request (BulkReingestRequest | None): The subset to re-run; omit for the whole collection.
                Set ``request.force`` to bypass the stage cache and recompute every stage.

        Returns:
            BulkReingestAccepted: matched / enqueued / capped + one job handle per enqueued run.
        """
        return self._transport.request(
            self._reingest_spec(collection_id, request or BulkReingestRequest()),
            BulkReingestAccepted,
        )

    def estimate(
        self,
        collection_id: str,
        scope: Literal["pending", "all"] = "pending",
        document_ids: list[str] | None = None,
        filter: DocumentFilter | None = None,
    ) -> CostEstimate:
        """
        Project a collection's ingestion cost and volume before spending a cent.

        Args:
            collection_id (str): The collection to estimate over.
            scope (str): Whole-collection selector used when neither subset below is given —
                ``pending`` (not-yet-ingested, the default) or ``all`` (every document).
            document_ids (list[str] | None): Estimate over exactly these document ids (mutually
                exclusive with ``filter``; overrides ``scope`` when set).
            filter (DocumentFilter | None): Estimate over the documents matching this corpus filter
                (mutually exclusive with ``document_ids``; overrides ``scope`` when set).

        Returns:
            CostEstimate: The per-stage breakdown, projected volume, totals, assumptions and caveats.
        """
        request = CollectionEstimateRequest(scope=scope, document_ids=document_ids, filter=filter)
        return self._transport.request(self._estimate_spec(collection_id, request), CostEstimate)


__all__ = ["AsyncCollections", "SyncCollections"]
