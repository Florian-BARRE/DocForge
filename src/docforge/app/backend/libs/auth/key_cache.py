# ====== Code Summary ======
# A tiny in-process TTL cache for the authentication hot path. `authenticate()` looks an API key up
# by its SHA-256 hash on EVERY `/api/v1` request; hashing is cheap, the Postgres read is not. This
# caches the resolved `(key row, owning user)` tuple — AND negative (unknown-key) results — keyed by
# hash for a short TTL (`RUNTIME_CONFIG.AUTH_KEY_CACHE_TTL_SECONDS`, default 10s; 0 disables). The
# negative entry blunts a credential-flood 401 storm from hammering the DB. A revoked/deactivated key
# therefore keeps authenticating for AT MOST TTL seconds in a given process — an accepted staleness
# window, settable to 0 to disable entirely; a same-process write (e.g. key rotation) best-effort
# evicts its own hash so the app reflects its OWN mutation immediately (other replicas/the worker
# still wait out the TTL). Correct under asyncio WITHOUT a lock: `get`/`put`/`evict` are fully
# synchronous (no `await` between reading and writing the dict), so the single-threaded event loop
# never interleaves a read with a concurrent write — this is a read-mostly cache, a plain dict with
# monotonic deadlines suffices.

# ====== Standard Library Imports ======
import time
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG


class AuthKeyCache(LoggerClass):
    """
    Short-TTL in-process cache of API-key lookups, keyed by the key's SHA-256 hash.

    Stores both positive `(key, user)` resolutions and negative (unknown-key) results for the same
    TTL. The TTL is read live from ``RUNTIME_CONFIG.AUTH_KEY_CACHE_TTL_SECONDS`` on every access so a
    runtime override (and ``0`` = disabled) takes effect without reconstruction. Entries are evicted
    lazily on read once their monotonic deadline passes.
    """

    def __init__(self) -> None:
        """Initialize an empty cache."""
        LoggerClass.__init__(self)
        # 1. hash -> (monotonic_deadline, resolved_value). resolved_value is the (key, user) tuple
        #    or None (a cached negative result). Lazily pruned on read past its deadline.
        self._entries: dict[str, tuple[float, Any]] = {}

    def get(self, key_hash: str) -> tuple[bool, Any]:
        """
        Look a key hash up in the cache.

        Args:
            key_hash (str): The SHA-256 hash of the presented bearer token.

        Returns:
            tuple[bool, Any]: ``(hit, value)``. ``hit`` is False on a miss (absent, expired, or the
            cache disabled) and the caller must read the store. On a hit ``value`` is the cached
            resolution — which may legitimately be ``None`` for a cached negative (unknown-key) result.
        """
        # 1. Disabled (TTL <= 0) → always a miss; never serve a cached value under a zero TTL.
        if RUNTIME_CONFIG.AUTH_KEY_CACHE_TTL_SECONDS <= 0:
            return False, None

        # 2. Absent → miss.
        entry = self._entries.get(key_hash)
        if entry is None:
            return False, None

        # 3. Expired → drop and miss (lazy eviction bounds the dict for one-shot hashes).
        deadline, value = entry
        if time.monotonic() >= deadline:
            self._entries.pop(key_hash, None)
            return False, None

        # 4. Fresh hit — hand back the cached resolution (possibly a negative None).
        return True, value

    def put(self, key_hash: str, value: Any) -> None:
        """
        Store a key-lookup result under a fresh TTL deadline.

        Args:
            key_hash (str): The SHA-256 hash of the presented bearer token.
            value (Any): The resolved ``(key, user)`` tuple, or ``None`` for an unknown key.
        """
        # 1. Disabled → never store (keeps the cache empty and every request store-bound).
        ttl = RUNTIME_CONFIG.AUTH_KEY_CACHE_TTL_SECONDS
        if ttl <= 0:
            return

        # 2. Stamp a monotonic deadline and store (positive AND negative results alike).
        self._entries[key_hash] = (time.monotonic() + ttl, value)

    def evict(self, key_hash: str) -> None:
        """
        Best-effort drop of a single cached entry (a no-op when absent).

        Lets a same-process mutation of a key (e.g. rotation) reflect immediately rather than after
        the TTL elapses. Other processes (the worker, another replica) still wait out the TTL.

        Args:
            key_hash (str): The hash whose cached entry should be removed.
        """
        # 1. Drop it if present; a missing entry is a harmless no-op.
        self._entries.pop(key_hash, None)

    def clear(self) -> None:
        """Drop every cached entry (used by tests to isolate the shared process-level cache)."""
        # 1. Wipe the whole cache.
        self._entries.clear()


__all__ = ["AuthKeyCache"]
