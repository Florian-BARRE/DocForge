# ====== Code Summary ======
# GENERATED FILE — DO NOT EDIT. Derived from async_collection_aliases.py by scripts/generate_sync.py;
# regenerate with `uv run --frozen python scripts/generate_sync.py` from src/docforge_sdk
# (tests/unit/test_sync_codegen.py fails when this file drifts from its async source).
# The synchronous collection aliases resource: the blocking shell over the shared
# ``_CollectionAliasesSpecs`` builders.

# ====== Local Project Imports ======
from ...models.collection_aliases import (
    CollectionAliasModel,
    SetCollectionAliasResponse,
)
from .._base import SyncResource
from .specs import _CollectionAliasesSpecs


class SyncCollectionAliases(SyncResource, _CollectionAliasesSpecs):
    """Synchronous collection aliases."""

    def list(self) -> list[CollectionAliasModel]:
        """
        List the collection aliases whose target the caller may see, by name.

        Returns:
            list[CollectionAliasModel]: Each alias with its current target (id + name).
        """
        return self._transport.request(self._list_spec(), list[CollectionAliasModel])

    def set(self, name: str, collection_id: str) -> SetCollectionAliasResponse:
        """
        Create the alias, or atomically re-point it to another collection (the "switch").

        Args:
            name (str): The alias slug (lowercase letters, digits, '-', '_').
            collection_id (str): The UUID of the collection the alias must target.

        Returns:
            SetCollectionAliasResponse: The alias now + its previous target (None = created).
        """
        return self._transport.request(
            self._set_spec(name, collection_id), SetCollectionAliasResponse
        )

    def delete(self, name: str) -> None:
        """
        Delete a collection alias (keys scoped ``alias:<name>`` then grant nothing through it).

        Args:
            name (str): The alias name.
        """
        self._transport.request(self._delete_spec(name), type(None))
