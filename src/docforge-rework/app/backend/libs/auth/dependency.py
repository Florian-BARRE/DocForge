# ====== Code Summary ======
# The authentication gate — a FastAPI dependency resolving each request to an AuthPrincipal. With
# auth DISABLED it short-circuits to a synthetic full-access root (dev default, no credential). With
# auth ENABLED it reads the `Authorization: Bearer <token>` header, looks the key up by its
# deterministic hash, and rejects a missing/revoked key or an inactive owning account with 401. All
# 401s carry `WWW-Authenticate: Bearer`. Per-scope authorization (which collections/capabilities a
# key may touch) is Lot 2 — here a valid, active key grants access.

# ====== Third-Party Library Imports ======
from fastapi import HTTPException, Request

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG

# ====== Local Project Imports ======
from ...context import CONTEXT
from .keys import AuthKeys
from .principal import AuthPrincipal

# The bearer scheme prefix expected on the Authorization header.
_BEARER_PREFIX = "Bearer "
# One opaque message for every credential failure — never reveal WHICH check failed.
_INVALID_CREDENTIAL = "Invalid or revoked API key."


def _unauthorized(detail: str) -> HTTPException:
    """
    Build a 401 that advertises the bearer scheme.

    Args:
        detail (str): The client-facing reason.

    Returns:
        HTTPException: A 401 carrying the WWW-Authenticate challenge header.
    """
    return HTTPException(
        status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"}
    )


def _extract_bearer(request: Request) -> str:
    """
    Extract the bearer token from the Authorization header.

    Args:
        request (Request): The incoming request.

    Returns:
        str: The raw token.

    Raises:
        HTTPException: 401 when the header is absent, not a bearer, or empty.
    """
    # 1. The header must be present and use the bearer scheme.
    header = request.headers.get("Authorization")
    if not header or not header.startswith(_BEARER_PREFIX):
        raise _unauthorized("Missing or malformed bearer token.")

    # 2. Strip the scheme; an empty remainder is malformed.
    token = header[len(_BEARER_PREFIX) :].strip()
    if not token:
        raise _unauthorized("Missing or malformed bearer token.")
    return token


async def authenticate(request: Request) -> AuthPrincipal:
    """
    Resolve the request to an authenticated principal (the global authN gate).

    Args:
        request (Request): The incoming request.

    Returns:
        AuthPrincipal: The synthetic root when auth is off, otherwise the verified key + user.

    Raises:
        HTTPException: 401 when a required credential is missing, revoked, or its owner inactive.
    """
    # 1. Auth off (dev default) → uniform synthetic full-access principal, no credential needed.
    if not RUNTIME_CONFIG.AUTH_ENABLED:
        return AuthPrincipal.synthetic_root()

    # 2. Read the bearer token (401 if absent/malformed).
    token = _extract_bearer(request)

    # 3. Resolve the key AND its owner in ONE joined round-trip. A missing key OR a missing owner
    #    row both come back as None here (the inner join collapses them) — one opaque 401.
    resolved = await CONTEXT.database.auth.get_key_with_user(AuthKeys.hash_key(token))
    if resolved is None:
        raise _unauthorized(_INVALID_CREDENTIAL)
    key, user = resolved

    # 4. A revoked key or an inactive owner denies with the SAME opaque failure (never reveal which).
    if key.revoked_at is not None or not user.is_active:
        raise _unauthorized(_INVALID_CREDENTIAL)

    # 5. Authenticated — carry the key + user; full-access derives from NULL permissions.
    return AuthPrincipal.from_key(key, user)


__all__ = ["authenticate"]
