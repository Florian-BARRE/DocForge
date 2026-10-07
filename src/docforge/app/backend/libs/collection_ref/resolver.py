# ====== Code Summary ======
# CollectionRefResolver — turns a collection REF (a collection UUID, or a collection alias name) into the
# collection UUID. It backs three FastAPI dependencies — the `{collection_id}` PATH param of every
# collection-scoped route, and the `collection_id` QUERY param of the job/ops routes (required or
# optional) — exposed as the `CollectionRef*` annotated types the routes declare. A UUID-shaped ref is
# returned as-is (routes keep their own 404 on an unknown id); an alias is looked up UNCACHED across
# requests (a re-point is effective on the very next request) and memoised for the current request only,
# so the authZ gate and the route share one lookup. An unknown alias — or a ref that is neither a UUID
# nor a well-formed alias name (looked up never) — is a 404. The resolved id is also
# stashed on the request state so the audit trail can attribute an alias-addressed mutation to its id.

# ====== Standard Library Imports ======
import uuid
from typing import Annotated

# ====== Third-Party Library Imports ======
from fastapi import Depends, HTTPException, Path, Query, Request

# ====== Local Project Imports ======
from ...context import CONTEXT
from .alias_name import CollectionAliasName

# Per-request memo of resolved refs (request.state attribute) — never shared across requests.
_MEMO_ATTR = "collection_refs"
# The resolved target of the request's collection ref, read back by the audit middleware.
RESOLVED_STATE_KEY = "resolved_collection_id"

_REF_DESCRIPTION = "The collection UUID, or the name of a collection alias pointing at it."


# The id an unknown alias resolves to for a scoped caller: never a real collection, never in scope.
_UNRESOLVED = uuid.UUID(int=0)


class CollectionRefResolver:
    """Static resolution of a collection ref (UUID or alias name) to the collection UUID."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("CollectionRefResolver is a static-only class and cannot be instantiated.")

    @staticmethod
    def is_uuid_ref(ref: str) -> bool:
        """Tell whether a ref is a collection UUID (as opposed to an alias name)."""
        try:
            uuid.UUID(ref)
        except ValueError:
            return False
        return True

    @staticmethod
    async def lookup(request: Request, ref: str) -> uuid.UUID | None:
        """
        Resolve a ref, or None when it is an unknown alias.

        Args:
            request (Request): The live request (carries the per-request memo).
            ref (str): A collection UUID or an alias name.

        Returns:
            uuid.UUID | None: The collection id (a UUID ref is returned unverified).
        """
        # 1. A UUID ref is the id itself — no lookup (the route 404s an unknown id as before).
        try:
            return uuid.UUID(ref)
        except ValueError:
            pass

        # 2. A ref outside the alias grammar can name nothing — no lookup.
        if CollectionAliasName.problem(ref) is not None:
            return None

        # 3. Per-request memo: the authZ gate and the route dependency resolve the same ref once.
        memo: dict[str, uuid.UUID | None] = getattr(request.state, _MEMO_ATTR, None) or {}
        if ref not in memo:
            targets = await CONTEXT.database.collection_aliases.targets_of([ref])
            memo[ref] = targets.get(ref)
            setattr(request.state, _MEMO_ATTR, memo)
        return memo[ref]

    @classmethod
    async def resolve(cls, request: Request, ref: str) -> uuid.UUID:
        """
        Resolve a ref to the collection id, 404 when it names no alias.

        Args:
            request (Request): The live request.
            ref (str): A collection UUID or an alias name.

        Returns:
            uuid.UUID: The collection id.

        Raises:
            HTTPException: 404 for an unknown alias (or a malformed ref).
        """
        # 1. Resolve, then remember the target for the audit trail. For a SCOPED caller an unknown
        #    alias is not answered here: the route's parameters resolve BEFORE its authz gate, so a
        #    404 here would let a key lacking the route's capability tell unknown aliases (404) from
        #    existing ones (the gate's 403). The nil id defers the verdict to the gate, which checks
        #    the capability first and then answers an unknown OR out-of-scope alias the same 404.
        collection_id = await cls.lookup(request, ref)
        if collection_id is None:
            principal = getattr(request.state, "principal", None)
            if principal is not None and not principal.is_full_access:
                return _UNRESOLVED
            raise HTTPException(status_code=404, detail=f"Collection '{ref}' not found.")
        setattr(request.state, RESOLVED_STATE_KEY, str(collection_id))
        return collection_id

    @classmethod
    async def from_path(
        cls, request: Request, collection_id: str = Path(description=_REF_DESCRIPTION)
    ) -> uuid.UUID:
        """The ``{collection_id}`` path-param dependency (UUID or alias name)."""
        return await cls.resolve(request, collection_id)

    @classmethod
    async def from_query(
        cls, request: Request, collection_id: str = Query(description=_REF_DESCRIPTION)
    ) -> uuid.UUID:
        """A required ``collection_id`` query-param dependency (UUID or alias name)."""
        return await cls.resolve(request, collection_id)

    @classmethod
    async def from_optional_query(
        cls,
        request: Request,
        collection_id: str | None = Query(
            default=None, description=f"{_REF_DESCRIPTION} Omitted = fleet-wide."
        ),
    ) -> uuid.UUID | None:
        """An optional ``collection_id`` query-param dependency (absent = fleet-wide)."""
        if collection_id is None:
            return None
        return await cls.resolve(request, collection_id)


# The annotated parameter types routes declare in place of ``uuid.UUID``.
CollectionRef = Annotated[uuid.UUID, Depends(CollectionRefResolver.from_path)]
CollectionRefQuery = Annotated[uuid.UUID, Depends(CollectionRefResolver.from_query)]
OptionalCollectionRefQuery = Annotated[
    uuid.UUID | None, Depends(CollectionRefResolver.from_optional_query)
]


__all__ = [
    "RESOLVED_STATE_KEY",
    "CollectionRef",
    "CollectionRefQuery",
    "CollectionRefResolver",
    "OptionalCollectionRefQuery",
]
