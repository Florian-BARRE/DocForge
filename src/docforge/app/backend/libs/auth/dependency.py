# ====== Code Summary ======
# The authentication gate — a FastAPI dependency resolving each request to an AuthPrincipal. With
# auth DISABLED it short-circuits to a synthetic full-access root (dev default, no credential). With
# auth ENABLED it reads the `Authorization: Bearer <token>` header, looks the key up by its
# deterministic hash, and rejects a missing/revoked/expired key or an inactive owning account with
# 401. All 401s carry `WWW-Authenticate: Bearer`. On a successful authentication it also records the
# key's last-used instant (throttled + best-effort — a metrics write never fails a valid request).
# Per-scope authorization (which collections/capabilities a key may touch) is Lot 2 — here a valid,
# active, unexpired key grants access.

# ====== Standard Library Imports ======
from datetime import UTC, datetime, timedelta
from typing import Any

# ====== Third-Party Library Imports ======
from fastapi import HTTPException, Request

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG

# ====== Local Project Imports ======
from ...context import CONTEXT
from .key_cache import AuthKeyCache
from .keys import AuthKeys
from .principal import AuthPrincipal

# The bearer scheme prefix expected on the Authorization header.
_BEARER_PREFIX = "Bearer "
# One opaque message for every credential failure — never reveal WHICH check failed.
_INVALID_CREDENTIAL = "Invalid or revoked API key."
# Minimum interval between two last_used_at writes for the same key — avoids a write per request.
_LAST_USED_THROTTLE_SECONDS = 60

# Process-level cache of the by-hash key lookup (the authN gate is a module function, not a class, so
# its cache lives at module scope alongside it). Short TTL (RUNTIME_CONFIG.AUTH_KEY_CACHE_TTL_SECONDS)
# keeps an authenticated request off Postgres; a revoked/deactivated key stays valid for at most that
# TTL — accepted, 0 disables. See key_cache.py.
_KEY_CACHE = AuthKeyCache()


def _unauthorized(detail: str) -> HTTPException:
    """
    Build a 401 that advertises the bearer scheme.

    Args:
        detail (str): The client-facing reason.

    Returns:
        HTTPException: A 401 carrying the WWW-Authenticate challenge header.
    """
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


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


def _is_last_used_stale(last_used_at: datetime | None, now: datetime) -> bool:
    """
    Decide whether a key's last_used_at is stale enough to warrant a fresh write.

    Args:
        last_used_at (datetime | None): The stored last-used instant (None = never used).
        now (datetime): The current instant (tz-aware).

    Returns:
        bool: True when the key was never used or the throttle window has elapsed.
    """
    # 1. Never-used keys always warrant a first stamp.
    if last_used_at is None:
        return True

    # 2. Guard a naive value (Postgres timestamptz is tz-aware, but stay correct if it isn't).
    if last_used_at.tzinfo is None:
        last_used_at = last_used_at.replace(tzinfo=UTC)

    # 3. Only write once the throttle window has fully elapsed.
    return (now - last_used_at) >= timedelta(seconds=_LAST_USED_THROTTLE_SECONDS)


def _is_expired(expires_at: datetime | None, now: datetime) -> bool:
    """
    Decide whether a key's expiry instant has passed.

    Args:
        expires_at (datetime | None): The stored expiry instant (None = never expires).
        now (datetime): The current instant (tz-aware).

    Returns:
        bool: True when the key carries an expiry that is at or before ``now``.
    """
    # 1. No expiry set — the key never expires.
    if expires_at is None:
        return False

    # 2. Guard a naive value (Postgres timestamptz is tz-aware, but stay correct if it isn't).
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    # 3. Expired once the instant is reached.
    return expires_at <= now


async def _touch_last_used(key: Any, now: datetime) -> None:
    """
    Best-effort record of a key's last successful authentication (never fails the request).

    Args:
        key (Any): The authenticated key row (id + last_used_at are read/updated in place).
        now (datetime): The authentication instant to record when stale.
    """
    # 1. Throttled — skip the write when a recent stamp already exists.
    if not _is_last_used_stale(key.last_used_at, now):
        return

    # 2. Swallow ANY failure: a metrics write must never turn a valid request into a 500.
    try:
        await CONTEXT.database.auth.touch_key_last_used(key.id, now)
    except Exception as exc:
        CONTEXT.logger.warning(f"Failed to record last_used_at for key {key.id}: {exc}")
        return

    # 3. Reflect the fresh stamp on the (possibly cached) key object, so a subsequent cache HIT
    #    within the TTL window re-applies the 60s throttle instead of re-writing on every request.
    key.last_used_at = now


async def _resolve_key(key_hash: str) -> tuple[Any, Any] | None:
    """
    Resolve a key + owning user by hash, via the short-TTL cache with a DB fallback on a miss.

    Args:
        key_hash (str): The SHA-256 hash of the presented bearer token.

    Returns:
        tuple[Any, Any] | None: The ``(key, user)`` pair, or ``None`` when no active key+owner
        matches the hash (the inner join collapses a missing key OR owner to ``None``).
    """
    # 1. Serve a fresh cached result (positive OR negative) without touching Postgres.
    hit, cached = _KEY_CACHE.get(key_hash)
    if hit:
        return cached

    # 2. Miss → one joined DB read; cache the outcome (including None) for the TTL window so a
    #    repeat request — or a credential-flood retry of the same bad key — stays off the store.
    resolved = await CONTEXT.database.auth.get_key_with_user(key_hash)
    _KEY_CACHE.put(key_hash, resolved)
    return resolved


def evict_cached_key(key_hash: str) -> None:
    """
    Drop a key's cached lookup so a same-process mutation of it takes effect immediately.

    Best-effort: other processes (the worker, another replica) still wait out the TTL. Called by the
    keys router when it holds the affected hash (e.g. revoking the old key during a rotation).

    Args:
        key_hash (str): The hash whose cached entry should be evicted.
    """
    # 1. Forward to the process-level cache (a no-op when the entry is absent or the cache disabled).
    _KEY_CACHE.evict(key_hash)


async def authenticate(request: Request) -> AuthPrincipal:
    """
    Resolve the request to an authenticated principal (the global authN gate).

    Args:
        request (Request): The incoming request.

    Returns:
        AuthPrincipal: The synthetic root when auth is off, otherwise the verified key + user.

    Raises:
        HTTPException: 401 when a required credential is missing, revoked, expired, or its owner
            inactive.
    """
    # 1. Auth off (dev default) → uniform synthetic full-access principal, no credential needed.
    if not RUNTIME_CONFIG.AUTH_ENABLED:
        return AuthPrincipal.synthetic_root()

    # 2. Read the bearer token (401 if absent/malformed).
    token = _extract_bearer(request)

    # 3. Resolve the key AND its owner in ONE joined round-trip, served from the short-TTL cache when
    #    fresh (skips Postgres on the hot path). A missing key OR a missing owner row both come back
    #    as None here (the inner join collapses them) — one opaque 401.
    resolved = await _resolve_key(AuthKeys.hash_key(token))
    if resolved is None:
        raise _unauthorized(_INVALID_CREDENTIAL)
    key, user = resolved

    # 4. A revoked, expired, or orphaned/inactive key denies with the SAME opaque failure (never
    #    reveal WHICH check failed). These checks run on EVERY request (cached or not), against a
    #    fresh `now` — so an expiry that passes mid-TTL is still honoured; a revocation/deactivation
    #    that lands mid-TTL is tolerated for at most the TTL (accepted staleness, see key_cache.py).
    now = datetime.now(UTC)
    if key.revoked_at is not None or _is_expired(key.expires_at, now) or not user.is_active:
        raise _unauthorized(_INVALID_CREDENTIAL)

    # 5. Record the successful use (throttled, best-effort — never blocks/fails the request).
    await _touch_last_used(key, now)

    # 6. Authenticated — carry the key + user; full-access derives from NULL permissions.
    return AuthPrincipal.from_key(key, user)


__all__ = ["authenticate", "evict_cached_key"]
