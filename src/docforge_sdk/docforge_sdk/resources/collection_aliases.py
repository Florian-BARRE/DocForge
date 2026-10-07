# ====== Code Summary ======
# The collection-alias resource — list the aliases (name → current target), create or atomically
# re-point one (the "switch": every key scoped `alias:<name>` and every client addressing the alias
# follow it on the next request), and delete one. URL logic lives once in the pure
# _CollectionAliasesSpecs mixin so the async/sync shells differ ONLY by ``await``.

# ====== Local Project Imports ======
from .._requestspec import RequestSpec
from ..models.collection_aliases import (
    CollectionAliasModel,
    SetCollectionAliasRequest,
    SetCollectionAliasResponse,
)
from ._base import AsyncResource, SyncResource, _ResourceMixin


class _CollectionAliasesSpecs(_ResourceMixin):
    """Pure ``RequestSpec`` builders for the collection-alias endpoints."""

    _BASE = "/collection-aliases"

    def _list_spec(self) -> RequestSpec:
        """A GET of every alias the caller may see."""
        return RequestSpec("GET", self._BASE)

    def _set_spec(self, name: str, collection_id: str) -> RequestSpec:
        """A PUT creating / re-pointing ``name`` to ``collection_id``."""
        body = SetCollectionAliasRequest(collection_id=collection_id)
        return RequestSpec("PUT", f"{self._BASE}/{name}", json=body.model_dump(mode="json"))

    def _delete_spec(self, name: str) -> RequestSpec:
        """A DELETE of one alias."""
        return RequestSpec("DELETE", f"{self._BASE}/{name}")


class AsyncCollectionAliases(AsyncResource, _CollectionAliasesSpecs):
    """Asynchronous collection aliases."""

    async def list(self) -> list[CollectionAliasModel]:
        """
        List the collection aliases whose target the caller may see, by name.

        Returns:
            list[CollectionAliasModel]: Each alias with its current target (id + name).
        """
        return await self._transport.request(self._list_spec(), list[CollectionAliasModel])

    async def set(self, name: str, collection_id: str) -> SetCollectionAliasResponse:
        """
        Create the alias, or atomically re-point it to another collection (the "switch").

        Args:
            name (str): The alias slug (lowercase letters, digits, '-', '_').
            collection_id (str): The UUID of the collection the alias must target.

        Returns:
            SetCollectionAliasResponse: The alias now + its previous target (None = created).
        """
        return await self._transport.request(
            self._set_spec(name, collection_id), SetCollectionAliasResponse
        )

    async def delete(self, name: str) -> None:
        """
        Delete a collection alias (keys scoped ``alias:<name>`` then grant nothing through it).

        Args:
            name (str): The alias name.
        """
        await self._transport.request(self._delete_spec(name), type(None))


class SyncCollectionAliases(SyncResource, _CollectionAliasesSpecs):
    """Synchronous collection aliases."""

    def list(self) -> list[CollectionAliasModel]:
        """List the collection aliases (see the async twin)."""
        return self._transport.request(self._list_spec(), list[CollectionAliasModel])

    def set(self, name: str, collection_id: str) -> SetCollectionAliasResponse:
        """Create or atomically re-point an alias (see the async twin)."""
        return self._transport.request(
            self._set_spec(name, collection_id), SetCollectionAliasResponse
        )

    def delete(self, name: str) -> None:
        """Delete a collection alias (see the async twin)."""
        self._transport.request(self._delete_spec(name), type(None))


__all__ = ["AsyncCollectionAliases", "SyncCollectionAliases"]
