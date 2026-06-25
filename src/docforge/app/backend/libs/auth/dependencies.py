# ====== Code Summary ======
# FastAPI dependencies for the auth layer. These are the only auth touch-points routers see:
#   - require_principal: authenticate the request (or inject a synthetic root when auth is off).
#   - require_root: gate root-only routes.
#   - require_collection_role(min_role): factory gating a collection-scoped route by effective role.
# All business logic lives in AuthService (accessed via CONTEXT) — dependencies only translate its
# results into 401 / 403 / 404 HTTP outcomes with verbose, explicit comments.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from typing import Any

# ====== Third-Party Library Imports ======
from fastapi import Depends, HTTPException, Request

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from common_libs.storage.postgres.models import GrantRole, UserRole

# ====== Local Project Imports ======
from .models import Principal

# Per-collection role ordering (read < write < admin). Used to compare a caller's effective role
# against a route's minimum required role. Higher number = more privileged.
_ROLE_RANK: dict[GrantRole, int] = {
    GrantRole.READ: 0,
    GrantRole.WRITE: 1,
    GrantRole.ADMIN: 2,
}

# Synthetic principal injected when AUTH_ENABLED is false — a stable, all-powerful root identity so
# the API behaves exactly as it did before auth existed. Its fixed nil-UUID makes it recognizable in
# logs and never collides with a real user (real ids are random UUID4).
_DISABLED_AUTH_PRINCIPAL = Principal(
    user_id=uuid.UUID(int=0),
    username="auth-disabled-root",
    global_role=UserRole.ROOT,
    is_root=True,
)


def _extract_bearer(request: Request, query_token: str | None = None) -> str | None:
    """
    Pull the raw Bearer credential out of the Authorization header.

    The optional ``query_token`` fallback exists ONLY for SSE routes: a browser ``EventSource``
    cannot send an Authorization header, so those routes pass the ``?token=`` query value in
    explicitly. The header always wins; the query fallback is never read for any route that does
    not opt in (tokens in query strings can end up in access logs).

    Args:
        request (Request): The incoming request.
        query_token (str | None): An explicit fallback credential (SSE routes only). Default None.

    Returns:
        str | None: The token value with the ``Bearer `` scheme stripped, the query fallback, or
        None when neither is present (or the header uses a non-Bearer scheme).
    """
    # 1. Read the header; accept only the Bearer scheme (case-insensitive)
    header = request.headers.get("Authorization")
    if header:
        scheme, _, value = header.partition(" ")
        if scheme.lower() == "bearer" and value:
            return value.strip()

    # 2. SSE-only explicit fallback (never populated for header-only routes)
    if query_token:
        return query_token.strip()
    return None


async def _authenticate(request: Request, query_token: str | None = None) -> Principal:
    """
    Shared credential-resolution core for the request-level auth dependencies.

    Applies the kill-switch, resolves the Bearer credential (header, or — only when ``query_token``
    is supplied by an SSE route — the query fallback) via AuthService, and stashes the result on
    ``request.state``. This is the single place the 401 outcome is produced.

    Args:
        request (Request): The incoming request.
        query_token (str | None): Explicit query-string credential (SSE routes only). Default None.

    Returns:
        Principal: The authenticated (or synthetic root) principal.

    Raises:
        HTTPException: 401 when auth is enabled and no valid credential is present.
    """
    # 1. Kill-switch: auth disabled → synthetic root, no credential needed
    if not CONTEXT.RUNTIME_CONFIG.AUTH_ENABLED:
        return _DISABLED_AUTH_PRINCIPAL

    # 2. Resolve the Bearer credential into a principal (same 3-step resolution for all callers)
    bearer = _extract_bearer(request, query_token=query_token)
    principal = await CONTEXT.auth_service.resolve_principal(bearer)
    if principal is None:
        # 401 — no credential, or the credential did not resolve to a live user.
        CONTEXT.logger.warning(
            f"Request rejected (401 unauthenticated): path={request.url.path}"
        )
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Stash the principal on request.state for downstream access (logging, MCP, etc.)
    request.state.principal = principal
    return principal


async def require_principal(request: Request) -> Principal:
    """
    Authenticate the request from the Authorization header and return its Principal.

    The default dependency for every protected route. When ``AUTH_ENABLED`` is false it injects a
    synthetic root (rétro-compat / open dev). Reads the credential ONLY from the Authorization
    header — query-string tokens are deliberately not accepted here (see ``require_principal_sse``).

    Args:
        request (Request): The incoming request (source of the Authorization header).

    Returns:
        Principal: The authenticated (or synthetic root) principal.

    Raises:
        HTTPException: 401 when auth is enabled and no valid credential is present.
    """
    # 1. Header-only authentication (no query fallback)
    return await _authenticate(request)


async def require_principal_sse(request: Request, token: str | None = None) -> Principal:
    """
    Authenticate an SSE route from the Authorization header OR a ``?token=`` query parameter.

    Browser ``EventSource`` cannot set request headers, so SSE endpoints accept the bearer credential
    as a ``token`` query parameter as a fallback. This dependency is used ONLY on the two SSE routes;
    the header still takes precedence and the resolution + 401 behavior are identical to
    ``require_principal``. Query-param auth is intentionally NOT broadened to any other route.

    Args:
        request (Request): The incoming request.
        token (str | None): The bearer credential passed as a query parameter (EventSource path).

    Returns:
        Principal: The authenticated (or synthetic root) principal.

    Raises:
        HTTPException: 401 when auth is enabled and no valid credential is present.
    """
    # 1. Header-or-query authentication (query fallback for header-less EventSource)
    return await _authenticate(request, query_token=token)


async def require_root(principal: Principal = Depends(require_principal)) -> Principal:
    """
    Gate a route to root users only.

    Args:
        principal (Principal): The authenticated principal (from ``require_principal``).

    Returns:
        Principal: The principal, guaranteed root.

    Raises:
        HTTPException: 403 when the principal is not root.
    """
    # 1. Only the global root role may pass
    if not principal.is_root:
        # 403 — authenticated but lacking the global root role required by this route.
        CONTEXT.logger.warning(
            f"Request rejected (403 root required): user_id={principal.user_id} "
            f"username={principal.username!r}"
        )
        raise HTTPException(status_code=403, detail="Root privileges required.")
    return principal


async def _enforce_collection_role(
    principal: Principal, collection_id: uuid.UUID, min_role: GrantRole
) -> Principal:
    """
    Enforce the minimum per-collection role for an already-authenticated principal.

    Shared by the header-only and media (header-or-query) collection gates so the 403 policy
    lives in one place.

    Args:
        principal (Principal): The authenticated principal.
        collection_id (uuid.UUID): The path's collection id.
        min_role (GrantRole): The minimum per-collection role required.

    Returns:
        Principal: The authorized principal.

    Raises:
        HTTPException: 403 when the caller has no grant on, or an insufficient role for, the
        collection. (A non-existent collection is surfaced as 403 here too — to avoid leaking
        existence; the route's own handler returns the precise 404 once authorization passes.)
    """
    # 1. Compute the caller's effective role (None = no grant at all)
    effective = await CONTEXT.auth_service.effective_collection_role(principal, collection_id)
    if effective is None:
        # 403 — the user holds no grant on this collection. We deliberately do NOT 404 here:
        # leaking "this collection exists" to a user with no access is an enumeration vector.
        CONTEXT.logger.warning(
            f"Request rejected (403 no grant): user_id={principal.user_id} "
            f"collection={collection_id} required={min_role.value}"
        )
        raise HTTPException(status_code=403, detail="You do not have access to this collection.")

    # 2. Compare the effective role against the route's minimum
    if _ROLE_RANK[effective] < _ROLE_RANK[min_role]:
        # 403 — the user has a grant but at a lower role than this route requires.
        CONTEXT.logger.warning(
            f"Request rejected (403 insufficient role): user_id={principal.user_id} "
            f"collection={collection_id} effective={effective.value} required={min_role.value}"
        )
        raise HTTPException(
            status_code=403,
            detail=f"This action requires the {min_role.value!r} role on the collection.",
        )

    return principal


def require_collection_role(
    min_role: GrantRole,
) -> Callable[..., Coroutine[Any, Any, Principal]]:
    """
    Build a dependency that gates a collection-scoped route by minimum effective role.

    Header-only authentication. The returned dependency reads ``collection_id`` from the path,
    computes the caller's effective role on that collection (root is implicitly admin), and
    enforces ``min_role``.

    Args:
        min_role (GrantRole): The minimum per-collection role required (read | write | admin).

    Returns:
        Callable: An async FastAPI dependency yielding the authorized Principal.
    """

    async def _dependency(
        collection_id: uuid.UUID,
        principal: Principal = Depends(require_principal),
    ) -> Principal:
        """Enforce the minimum collection role for the header-authenticated principal."""
        return await _enforce_collection_role(principal, collection_id, min_role)

    return _dependency


def require_collection_role_media(
    min_role: GrantRole,
) -> Callable[..., Coroutine[Any, Any, Principal]]:
    """
    Like :func:`require_collection_role`, but accepts the bearer credential from the Authorization
    header OR a ``?token=`` query parameter.

    Used ONLY for byte-returning media routes a browser loads via ``<img src>`` / direct navigation
    (e.g. the page screenshot), which cannot set an Authorization header — exactly the EventSource
    limitation that ``require_principal_sse`` addresses. The header still wins; query-param auth is
    not broadened to JSON routes (those go through the fetch client, which sends the header).

    Args:
        min_role (GrantRole): The minimum per-collection role required.

    Returns:
        Callable: An async FastAPI dependency yielding the authorized Principal.
    """

    async def _dependency(
        collection_id: uuid.UUID,
        request: Request,
        token: str | None = None,
    ) -> Principal:
        """Authenticate via header or ?token=, then enforce the minimum collection role."""
        # 1. Header-or-query authentication (query fallback for header-less <img> loads)
        principal = await _authenticate(request, query_token=token)
        # 2. Same per-collection role policy as the header-only gate
        return await _enforce_collection_role(principal, collection_id, min_role)

    return _dependency
