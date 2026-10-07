# ====== Code Summary ======
# The authorization gate — a `require(capability)` dependency factory layered ON TOP of the authN
# gate. Each returned dependency reuses the request-cached `authenticate` result (no second lookup),
# then enforces two things against the calling key: it must grant the demanded capability, and — when
# the endpoint carries a `collection_id` PATH param — it must be scoped to that collection. A full
# access principal (NULL-permission key, or the synthetic root produced when auth is disabled) bypasses
# every check, so the AUTH_ENABLED=false path is entirely unaffected. A stored key whose permissions
# blob is malformed is treated as granting NOTHING (deny), never a crash.
#
# The `collection_id` path param is a collection REF (UUID or collection-alias name): the async gate
# resolves an alias ref to its target id before the scope check. A key's own `alias:<name>` scope entries
# are evaluated against their per-request targets (`principal.alias_targets`) — a deleted alias grants
# nothing (fail closed).
#
# NOTE ON SCOPE: `enforce` collection-scopes ONLY the `collection_id` PATH param — the check it can
# make from the path alone. Endpoints whose collection lives in the request BODY/QUERY, or is derived after
# loading a resource (job/document/chunk/blob), close the gap by calling the `assert_collection_scope`
# / `assert_any_collection_scope` helpers once they know the target collection(s).

# ====== Standard Library Imports ======
from __future__ import annotations

from collections.abc import Awaitable, Callable

# ====== Third-Party Library Imports ======
from fastapi import HTTPException, Request
from loggerplusplus import loggerplusplus
from pydantic import ValidationError

# ====== Local Project Imports ======
from ..collection_ref import CollectionRefResolver
from .permissions import Capability, KeyPermissions
from .principal import AuthPrincipal

# The name of the path parameter that carries the collection scope, when present.
_COLLECTION_PATH_PARAM = "collection_id"


class AuthzGuard:
    """Static enforcement helpers for capability + collection-scope checks on a scoped key."""

    logger = loggerplusplus.bind(identifier="AuthzGuard")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("AuthzGuard is a static-only class and cannot be instantiated.")

    @staticmethod
    def __parse(principal: AuthPrincipal) -> KeyPermissions:
        """
        Parse the scoped key's stored permissions blob into its EFFECTIVE scope (aliases resolved).

        Args:
            principal (AuthPrincipal): The authenticated, non-full-access principal.

        Returns:
            KeyPermissions: The parsed scope, each ``alias:<name>`` entry replaced by the alias's
                current target (a dangling alias dropped — fail closed).

        Raises:
            HTTPException: 403 when the stored blob is malformed (treated as no grants, not a crash).
        """
        # 1. A non-full-access principal always carries a key with a dict permissions blob.
        raw = principal.key.permissions if principal.key is not None else None
        try:
            parsed = KeyPermissions.model_validate(raw)
        except ValidationError:
            # A corrupt/legacy shape must DENY, never 500 — the key is authorized for nothing.
            AuthzGuard.logger.warning(f"API key has a malformed permissions blob — denying")
            raise HTTPException(status_code=403, detail="API key has malformed permissions.")
        return parsed.with_resolved_aliases(principal.alias_targets)

    @classmethod
    def enforce(
        cls,
        capability: Capability,
        principal: AuthPrincipal,
        request: Request,
        collection_id: str | None = None,
    ) -> AuthPrincipal:
        """
        Authorize a principal for a capability and (when path-scoped) a collection.

        Args:
            capability (Capability): The capability the endpoint demands.
            principal (AuthPrincipal): The authenticated caller.
            request (Request): The live request (source of the ``collection_id`` path param).
            collection_id (str | None): The path ref ALREADY resolved to a collection id (the async
                gate passes it); None = read the raw path param (a UUID ref).

        Returns:
            AuthPrincipal: The same principal, unchanged, when authorized.

        Raises:
            HTTPException: 403 when the key lacks the capability or is not scoped to the collection.
        """
        # 1. Full access (NULL-permission key, or auth-off synthetic root) bypasses every check.
        if principal.is_full_access:
            return principal

        # 2. Parse the scoped key; a malformed blob denies here.
        permissions = cls.__parse(principal)

        # 3. The key must grant the demanded capability.
        if not permissions.grants_capability(capability):
            raise HTTPException(
                status_code=403, detail=f"API key lacks the '{capability}' capability."
            )

        # 4. Collection scoping — only when the endpoint carries a collection_id PATH param.
        if collection_id is None:
            collection_id = request.path_params.get(_COLLECTION_PATH_PARAM)
        if collection_id is not None and not permissions.grants_collection(str(collection_id)):
            raise HTTPException(
                status_code=403,
                detail=f"API key is not scoped to collection {collection_id}.",
            )

        # 5. Authorized.
        return principal

    @classmethod
    def holds(cls, principal: AuthPrincipal, capability: Capability) -> bool:
        """
        Tell whether a principal holds a capability — a soft check for in-route field shaping.

        Used where a route is reachable at a lower capability but some of its output is reserved
        to a higher one (e.g. ``get_collection`` omits the pipeline/search blobs for a key without
        READ_TECHNICAL) — the route degrades its payload instead of refusing.

        Args:
            principal (AuthPrincipal): The authenticated caller (already authorized for the route).
            capability (Capability): The capability gating the optional output.

        Returns:
            bool: True for a full-access principal or a scoped key granting ``capability``.

        Raises:
            HTTPException: 403 when the scoped key's permissions blob is malformed.
        """
        # 1. Full access holds everything; a scoped key holds what it explicitly grants.
        if principal.is_full_access:
            return True
        return cls.__parse(principal).grants_capability(capability)

    @classmethod
    def assert_collection_scope(cls, principal: AuthPrincipal, collection_id: str) -> None:
        """
        Enforce that a key may act on ONE collection resolved OUTSIDE the path (body/query/lookup).

        The path-param scope check in ``enforce`` cannot see a collection carried in the request
        body, a query param, or one derived after loading a resource (a job, a document, a chunk).
        Handlers call this once they know the target collection id, closing the cross-tenant gap.

        Args:
            principal (AuthPrincipal): The authenticated caller.
            collection_id (str): The collection the request actually targets.

        Raises:
            HTTPException: 403 when a scoped key is not scoped to ``collection_id`` (or its
                permissions blob is malformed).
        """
        # 1. Full access (root / auth-off synthetic) bypasses scoping entirely.
        if principal.is_full_access:
            return

        # 2. A scoped key must enumerate (or wildcard) the target collection.
        permissions = cls.__parse(principal)
        if not permissions.grants_collection(collection_id):
            raise HTTPException(
                status_code=403,
                detail=f"API key is not scoped to collection {collection_id}.",
            )

    @classmethod
    def scoped_collections(cls, principal: AuthPrincipal) -> set[str] | None:
        """
        Return the set of collection ids a principal may see, or None for unrestricted access.

        Used by fleet-wide endpoints (no ``collection_id`` in the path) that must NOT leak other
        tenants' resources: a ``None`` result means "every collection" (a full-access or wildcard
        key), while a concrete set is exactly the collections a scoped key is allowed to observe.

        Args:
            principal (AuthPrincipal): The authenticated caller.

        Returns:
            set[str] | None: The observable collection ids, or None when the key is unrestricted.

        Raises:
            HTTPException: 403 when the scoped key's permissions blob is malformed.
        """
        # 1. Full access (root / auth-off synthetic) sees every collection.
        if principal.is_full_access:
            return None

        # 2. A scoped key sees its enumerated set (None when it holds the wildcard).
        return cls.__parse(principal).scoped_collection_ids()

    @classmethod
    def assert_any_collection_scope(
        cls, principal: AuthPrincipal, collection_ids: list[str]
    ) -> None:
        """
        Enforce that a key is scoped to AT LEAST ONE of a set of candidate collections.

        Used for content-addressed resources with no single owner (a shared blob): a scoped key may
        reach it only when it owns one of the collections that reference it. An empty candidate set
        (an orphan or wholly foreign blob) therefore denies every scoped key — the safe default.

        Args:
            principal (AuthPrincipal): The authenticated caller.
            collection_ids (list[str]): The collections through which the resource is reachable.

        Raises:
            HTTPException: 403 when a scoped key owns none of ``collection_ids`` (or is malformed).
        """
        # 1. Full access bypasses scoping entirely.
        if principal.is_full_access:
            return

        # 2. A scoped key must own at least one referencing collection.
        permissions = cls.__parse(principal)
        if not any(permissions.grants_collection(cid) for cid in collection_ids):
            raise HTTPException(status_code=403, detail="API key is not scoped to this resource.")


def require(capability: Capability) -> Callable[..., Awaitable[AuthPrincipal]]:
    """
    Build a route dependency that enforces a capability (and path-scoped collection) on the key.

    The returned dependency reads the principal injected by ``AuthMiddleware`` into ``request.state``
    (the middleware is the authN gate; this per-endpoint gate answers "may you do this"). A full
    access principal bypasses all checks, so the AUTH_ENABLED=false path is untouched.

    Args:
        capability (Capability): The capability every request to the endpoint must carry.

    Returns:
        Callable[..., Awaitable[AuthPrincipal]]: An async FastAPI dependency yielding the principal.
    """

    async def _authorize(request: Request) -> AuthPrincipal:
        """Enforce ``capability`` (and collection scope) against the middleware-injected principal."""
        # 1. Read the principal the authN middleware injected; its absence is a wiring error, not a
        #    client fault — defensively reject with 401 (should never happen under the middleware).
        principal = getattr(request.state, "principal", None)
        if principal is None:
            raise HTTPException(
                status_code=401,
                detail="Not authenticated.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 2. Full access, or no collection in the path: the guard decides alone.
        ref = request.path_params.get(_COLLECTION_PATH_PARAM)
        if ref is None or principal.is_full_access:
            return AuthzGuard.enforce(capability, principal, request)

        # 3. A scoped key on a collection path: capability FIRST, so a key that may not call the
        #    route cannot use it to probe which alias names exist.
        if not AuthzGuard.holds(principal, capability):
            raise HTTPException(
                status_code=403, detail=f"API key lacks the '{capability}' capability."
            )

        # 4. Resolve the ref (UUID or alias; an unknown alias is a 404), then check the scope. An
        #    ALIAS outside the caller's scope answers the SAME 404 as an unknown one — never a 403
        #    naming its target id — so a scoped key can neither enumerate other tenants' aliases
        #    nor learn the collection ids behind them.
        resolved = str(await CollectionRefResolver.resolve(request, str(ref)))
        try:
            return AuthzGuard.enforce(capability, principal, request, collection_id=resolved)
        except HTTPException as exc:
            if exc.status_code == 403 and not CollectionRefResolver.is_uuid_ref(str(ref)):
                raise HTTPException(status_code=404, detail=f"Collection '{ref}' not found.")
            raise

    return _authorize


__all__ = ["require", "AuthzGuard"]
