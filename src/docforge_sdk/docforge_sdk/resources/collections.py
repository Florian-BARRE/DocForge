# ====== Code Summary ======
# The collections resource (CRUD over a collection's full contract). All URL/body logic lives once in
# the pure _CollectionsSpecs mixin, so AsyncCollections and SyncCollections have identical public
# surfaces whose bodies differ ONLY by ``await``.

# ====== Local Project Imports ======
from .._requestspec import RequestSpec
from ..models.collections import (
    CollectionModel,
    CreateCollectionRequest,
    UpdateCollectionRequest,
)
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


__all__ = ["AsyncCollections", "SyncCollections"]
