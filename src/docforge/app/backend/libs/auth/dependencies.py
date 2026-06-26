# ====== Code Summary ======
# FastAPI dependencies for the auth layer. These are the only auth touch-points routers see:
#   - require_principal: authenticate the request (or inject a synthetic root when auth is off).
#   - require_principal_sse: authenticate an SSE route (header OR ?token= query fallback).
#   - require_capability(cap): factory gating a collection-scoped route by a capability the caller's
#       API-key scope must grant on the path's collection.
#   - require_capability_media(cap): the same gate for byte-returning media routes (header OR ?token=).
# All business logic lives in AuthService (accessed via CONTEXT) + the capability taxonomy
# (capabilities.py); dependencies only translate results into 401 / 403 HTTP outcomes with verbose,
# explicit comments.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from typing import Any

# ====== Third-Party Library Imports ======
from fastapi import Depends, HTTPException, Request

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from common_libs.storage.postgres.models import UserRole

# ====== Local Project Imports ======
from .capabilities import Capability, CapabilityHelpers
from .models import Principal

# Synthetic principal injected when AUTH_ENABLED is false — a stable, all-powerful root identity so
# the API behaves exactly as it did before auth existed. Its fixed nil-UUID makes it recognizable in
# logs and never collides with a real user (real ids are random UUID4). permissions=None → full
# access (it bypasses every per-capability check).
_DISABLED_AUTH_PRINCIPAL = Principal(
    user_id=uuid.UUID(int=0),
    username="auth-disabled-root",
    global_role=UserRole.ROOT,
    is_root=True,
    permissions=None,
)


def _extract_bearer(request: Request, query_token: str | None = None) -> str | None:
    """
    Pull the raw Bearer credential out of the Authorization header.

    The optional ``query_token`` fallback exists ONLY for SSE / media routes: a browser
    ``EventSource`` or ``<img>`` cannot send an Authorization header, so those routes pass the
    ``?token=`` query value in explicitly. The header always wins; the query fallback is never read
    for any route that does not opt in (tokens in query strings can end up in access logs).

    Args:
        request (Request): The incoming request.
        query_token (str | None): An explicit fallback credential (SSE/media routes only).

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

    # 2. SSE/media-only explicit fallback (never populated for header-only routes)
    if query_token:
        return query_token.strip()
    return None


async def _authenticate(request: Request, query_token: str | None = None) -> Principal:
    """
    Shared credential-resolution core for the request-level auth dependencies.

    Applies the kill-switch, resolves the Bearer credential (header, or — only when ``query_token``
    is supplied by an SSE/media route — the query fallback) via AuthService, and stashes the result
    on ``request.state``. This is the single place the 401 outcome is produced.

    Args:
        request (Request): The incoming request.
        query_token (str | None): Explicit query-string credential (SSE/media routes only).

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
    as a ``token`` query parameter as a fallback. Used ONLY on the SSE routes; the header still takes
    precedence and the resolution + 401 behavior are identical to ``require_principal``.

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


def principal_grants_capability(
    principal: Principal, collection_id: uuid.UUID, capability: Capability
) -> bool:
    """
    Decide whether a principal is allowed a capability on a collection.

    The single authorization predicate shared by every collection-scoped gate (header, media, and
    the in-body SSE check). A full-access principal (root login, static root key, or a legacy
    null-permission key) is allowed everything; a scoped API key is allowed iff its permission
    entries grant the capability on this collection (its id or the ``*`` wildcard).

    Args:
        principal (Principal): The authenticated principal.
        collection_id (uuid.UUID): The path's collection id.
        capability (Capability): The capability the route requires.

    Returns:
        bool: True when the principal may perform the capability on the collection.
    """
    # 1. Full-access principals bypass per-capability checks
    if principal.has_full_access:
        return True

    # 2. Scoped API key — consult its permission entries
    return CapabilityHelpers.grants(principal.permissions or {}, str(collection_id), capability)


def _enforce_capability(
    principal: Principal, collection_id: uuid.UUID, capability: Capability
) -> Principal:
    """
    Enforce a capability for an already-authenticated principal, or raise 403.

    Shared by the header-only and media (header-or-query) collection gates so the 403 policy lives
    in one place.

    Args:
        principal (Principal): The authenticated principal.
        collection_id (uuid.UUID): The path's collection id.
        capability (Capability): The capability the route requires.

    Returns:
        Principal: The authorized principal.

    Raises:
        HTTPException: 403 when the key's scope does not grant the capability on the collection.
    """
    # 1. Allow full-access principals + scoped keys that grant the capability here
    if principal_grants_capability(principal, collection_id, capability):
        return principal

    # 2. 403 — the API key's scope does not grant this capability on this collection.
    CONTEXT.logger.warning(
        f"Request rejected (403 missing capability): user_id={principal.user_id} "
        f"collection={collection_id} required={capability.value}"
    )
    raise HTTPException(
        status_code=403,
        detail=(
            f"Your API key is not authorized for {capability.value!r} on this collection."
        ),
    )


def require_capability(
    capability: Capability,
) -> Callable[..., Coroutine[Any, Any, Principal]]:
    """
    Build a dependency that gates a collection-scoped route by a single capability.

    Header-only authentication. The returned dependency reads ``collection_id`` from the path,
    resolves the caller, and enforces that the caller's API-key scope grants ``capability`` on that
    collection (a full-access principal passes implicitly).

    Args:
        capability (Capability): The capability the route requires.

    Returns:
        Callable: An async FastAPI dependency yielding the authorized Principal.
    """

    async def _dependency(
        collection_id: uuid.UUID,
        principal: Principal = Depends(require_principal),
    ) -> Principal:
        """Enforce the required capability for the header-authenticated principal."""
        return _enforce_capability(principal, collection_id, capability)

    return _dependency


def require_capability_media(
    capability: Capability,
) -> Callable[..., Coroutine[Any, Any, Principal]]:
    """
    Like :func:`require_capability`, but accepts the bearer credential from the Authorization header
    OR a ``?token=`` query parameter.

    Used ONLY for byte-returning media routes a browser loads via ``<img src>`` / direct navigation
    (e.g. the page screenshot), which cannot set an Authorization header — the same EventSource
    limitation that ``require_principal_sse`` addresses. The header still wins; query-param auth is
    not broadened to JSON routes (those go through the fetch client, which sends the header).

    Args:
        capability (Capability): The capability the route requires.

    Returns:
        Callable: An async FastAPI dependency yielding the authorized Principal.
    """

    async def _dependency(
        collection_id: uuid.UUID,
        request: Request,
        token: str | None = None,
    ) -> Principal:
        """Authenticate via header or ?token=, then enforce the required capability."""
        # 1. Header-or-query authentication (query fallback for header-less <img> loads)
        principal = await _authenticate(request, query_token=token)
        # 2. Same per-capability policy as the header-only gate
        return _enforce_capability(principal, collection_id, capability)

    return _dependency
