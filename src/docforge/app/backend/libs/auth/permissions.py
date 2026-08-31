# ====== Code Summary ======
# The authorization vocabulary for scoped API keys. A `Capability` is a coarse action class an
# endpoint demands (READ / WRITE / SEARCH / ADMIN). A `KeyPermissions` is the parsed, validated shape
# stored in the key's JSONB `permissions` column: the capabilities the key grants and the collections
# it is scoped to (`["*"]` = all, else an explicit list of collection UUID strings). A NULL column
# (None) is NOT modelled here — it means unscoped full access and is handled upstream on the principal.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from enum import StrEnum

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field, field_validator

# The wildcard sentinel that scopes a key to every collection.
_ALL_COLLECTIONS = "*"


class Capability(StrEnum):
    """A coarse action class an endpoint requires of the calling key."""

    READ = "read"
    WRITE = "write"
    SEARCH = "search"
    # CREATE gates collection creation specifically. A scoped key that holds it gains ownership of
    # what it creates: the new collection's id is appended to its own `collections` scope, so a key
    # need not know ids up front to be given "may create + full power over what it creates".
    CREATE = "create"
    ADMIN = "admin"


class KeyPermissions(BaseModel):
    """
    The parsed per-key permission scope stored in the ``api_key.permissions`` JSONB column.

    A key with NULL permissions is full access (root) and never reaches this model — it is short
    circuited on the principal. This model therefore always describes a SCOPED key.

    Attributes:
        capabilities (list[Capability]): The action classes the key grants (an empty list = a key
            that can authenticate but is authorized for nothing).
        collections (list[str]): Either ``["*"]`` (every collection) or an explicit list of
            collection UUID strings the key is scoped to.
    """

    model_config = ConfigDict(extra="forbid")

    capabilities: list[Capability] = Field(
        description="The action classes this key grants (READ / WRITE / SEARCH / ADMIN)."
    )
    collections: list[str] = Field(
        description="Collection scope: ['*'] for all, else explicit collection UUID strings."
    )

    @field_validator("collections")
    @classmethod
    def _validate_collections(cls, value: list[str]) -> list[str]:
        """
        Enforce the collection-scope shape: a pure wildcard, or a list of valid UUID strings.

        Args:
            value (list[str]): The declared collection scope.

        Returns:
            list[str]: The validated scope, unchanged.

        Raises:
            ValueError: If the wildcard is mixed with explicit ids, or an entry is not a UUID.
        """
        # 1. The wildcard is all-or-nothing — mixing it with explicit ids is ambiguous.
        if _ALL_COLLECTIONS in value:
            if value != [_ALL_COLLECTIONS]:
                raise ValueError("collections wildcard '*' cannot be combined with explicit ids.")
            return value

        # 2. Every explicit entry must be a real collection UUID (rejects typos at write time).
        for entry in value:
            try:
                uuid.UUID(entry)
            except (ValueError, AttributeError, TypeError):
                raise ValueError(f"collection scope entry '{entry}' is not a valid UUID.")
        return value

    def grants_capability(self, capability: Capability) -> bool:
        """
        Tell whether this scope grants the given capability.

        Args:
            capability (Capability): The capability the endpoint demands.

        Returns:
            bool: True when the capability is present in this key's grants.
        """
        # 1. A scoped key grants only the capabilities explicitly listed.
        return capability in self.capabilities

    def grants_collection(self, collection_id: str) -> bool:
        """
        Tell whether this scope covers the given collection.

        Args:
            collection_id (str): The target collection id taken from the request path.

        Returns:
            bool: True when the key is wildcard-scoped or explicitly lists the collection.
        """
        # 1. Wildcard covers everything; otherwise the id must be explicitly enumerated.
        return _ALL_COLLECTIONS in self.collections or collection_id in self.collections

    def scoped_collection_ids(self) -> set[str] | None:
        """
        Return the explicit collection ids this key may see, or None when wildcard-scoped.

        A ``None`` result means "every collection" (the wildcard), letting a caller treat a
        wildcard key the same as full access. An explicit scope returns exactly its id set.

        Returns:
            set[str] | None: The scoped collection ids, or None for wildcard (all) scope.
        """
        # 1. Wildcard = unrestricted; otherwise the exact enumerated set.
        if _ALL_COLLECTIONS in self.collections:
            return None
        return set(self.collections)


__all__ = ["Capability", "KeyPermissions"]
