# ====== Code Summary ======
# The result + domain errors of the collection-alias façade: the outcome of a create/re-point write and
# the four refusals the router maps to HTTP (alias clashes with a collection name → 409, unknown target
# → 404, a concurrent same-name create → 409, and a collection delete refused while aliases target it
# → 409). Kept apart from the façade so the router and the collections façade import them cheaply.

# ====== Standard Library Imports ======
import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CollectionAliasWrite:
    """
    The outcome of an alias create / re-point.

    Attributes:
        name (str): The alias name.
        collection_id (uuid.UUID): The collection it now targets.
        previous_collection_id (uuid.UUID | None): The target before this write (None = created).
        created_at (datetime): When the alias was first created.
        updated_at (datetime): When it was last (re-)pointed.
    """

    name: str
    collection_id: uuid.UUID
    previous_collection_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class CollectionAliasNameClashError(Exception):
    """An alias name equals an existing collection's name (case-insensitive) — refused, 409."""

    def __init__(self, name: str, collection_name: str) -> None:
        super().__init__(
            f"Alias '{name}' clashes with the name of collection '{collection_name}'; aliases and "
            f"collection names must stay distinct."
        )
        self.name = name


class CollectionAliasTargetMissingError(Exception):
    """The collection an alias should point at does not exist — 404."""

    def __init__(self, collection_id: uuid.UUID) -> None:
        super().__init__(f"Collection {collection_id} not found.")
        self.collection_id = collection_id


class CollectionAliasConflictError(Exception):
    """A concurrent request created the same alias first — 409, retry the PUT."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Alias '{name}' was created concurrently; retry the request.")
        self.name = name


class CollectionAliasInUseError(Exception):
    """An alias delete refused while live API keys are scoped to it — 409.

    Deleting it would leave those keys naming a free alias name that anyone allowed to create an
    alias could then claim, silently re-binding the keys to that new target.
    """

    def __init__(self, name: str, key_count: int) -> None:
        super().__init__(
            f"Collection alias '{name}' is named by {key_count} live API key scope(s) "
            f"('alias:{name}'); re-scope or revoke those keys first, or re-point the alias instead."
        )
        self.name = name
        self.key_count = key_count


class CollectionAliasedError(Exception):
    """A collection delete refused because aliases still target it — 409."""

    def __init__(self, collection_id: uuid.UUID, aliases: list[str]) -> None:
        names = ", ".join(f"'{alias}'" for alias in aliases)
        super().__init__(
            f"Collection {collection_id} is the target of collection alias(es) {names}; re-point "
            f"or delete them first (PUT/DELETE /collection-aliases/{{name}})."
        )
        self.collection_id = collection_id
        self.aliases = aliases


__all__ = [
    "CollectionAliasConflictError",
    "CollectionAliasNameClashError",
    "CollectionAliasTargetMissingError",
    "CollectionAliasWrite",
    "CollectionAliasInUseError",
    "CollectionAliasedError",
]
