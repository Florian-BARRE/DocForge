# ====== Code Summary ======
# The asynchronous collection aliases resource: the awaiting shell over the shared
# ``_CollectionAliasesSpecs`` builders.

# ====== Local Project Imports ======
from ...models.collection_aliases import (
    CollectionAliasModel,
    SetCollectionAliasResponse,
)
from .._base import AsyncResource
from .specs import _CollectionAliasesSpecs


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
