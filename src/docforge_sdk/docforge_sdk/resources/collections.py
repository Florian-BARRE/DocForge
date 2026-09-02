# ====== Code Summary ======
# The collections resource (CRUD over a collection's full contract). All URL/body logic lives once in
# the pure _CollectionsSpecs mixin, so AsyncCollections and SyncCollections have identical public
# surfaces whose bodies differ ONLY by ``await``.

# ====== Standard Library Imports ======
from typing import Literal

# ====== Local Project Imports ======
from .._requestspec import RequestSpec
from ..models.collections import (
    BulkReingestAccepted,
    BulkReingestRequest,
    CollectionModel,
    CreateCollectionRequest,
    UpdateCollectionRequest,
)
from ..models.estimate import CollectionEstimateRequest, CostEstimate
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
            request (CollectionEstimateRequest): The scope (pending documents or all).

        Returns:
            RequestSpec: A POST on the collection's ``/estimate`` route with the scope body.
        """
        return RequestSpec(
            "POST",
            f"{self._COLLECTIONS_PATH}/{collection_id}/estimate",
            json=request.model_dump(mode="json"),
        )


class AsyncCollections(AsyncResource, _CollectionsSpecs):
    """Asynchronous collection management (list / get / create / update / delete)."""

    async def list(self) -> list[CollectionModel]:
        """
        List every collection with its full schema.

        Returns:
            list[CollectionModel]: All contracts, schema included.
        """
        return await self._transport.request(self._list_spec(), list[CollectionModel])

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

        Returns:
            BulkReingestAccepted: matched / enqueued / capped + one job handle per enqueued run.
        """
        return await self._transport.request(
            self._reingest_spec(collection_id, request or BulkReingestRequest()),
            BulkReingestAccepted,
        )

    async def estimate(
        self, collection_id: str, scope: Literal["pending", "all"] = "pending"
    ) -> CostEstimate:
        """
        Project a collection's ingestion cost and volume before spending a cent.

        Args:
            collection_id (str): The collection to estimate over.
            scope (str): Which documents to cover — ``pending`` (not-yet-ingested, the default) or
                ``all`` (every document in the collection).

        Returns:
            CostEstimate: The per-stage breakdown, projected volume, totals, assumptions and caveats.
        """
        return await self._transport.request(
            self._estimate_spec(collection_id, CollectionEstimateRequest(scope=scope)),
            CostEstimate,
        )


class SyncCollections(SyncResource, _CollectionsSpecs):
    """Synchronous collection management (list / get / create / update / delete)."""

    def list(self) -> list[CollectionModel]:
        """
        List every collection with its full schema.

        Returns:
            list[CollectionModel]: All contracts, schema included.
        """
        return self._transport.request(self._list_spec(), list[CollectionModel])

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

        Returns:
            BulkReingestAccepted: matched / enqueued / capped + one job handle per enqueued run.
        """
        return self._transport.request(
            self._reingest_spec(collection_id, request or BulkReingestRequest()),
            BulkReingestAccepted,
        )

    def estimate(
        self, collection_id: str, scope: Literal["pending", "all"] = "pending"
    ) -> CostEstimate:
        """
        Project a collection's ingestion cost and volume before spending a cent.

        Args:
            collection_id (str): The collection to estimate over.
            scope (str): Which documents to cover — ``pending`` (not-yet-ingested, the default) or
                ``all`` (every document in the collection).

        Returns:
            CostEstimate: The per-stage breakdown, projected volume, totals, assumptions and caveats.
        """
        return self._transport.request(
            self._estimate_spec(collection_id, CollectionEstimateRequest(scope=scope)),
            CostEstimate,
        )


__all__ = ["AsyncCollections", "SyncCollections"]
