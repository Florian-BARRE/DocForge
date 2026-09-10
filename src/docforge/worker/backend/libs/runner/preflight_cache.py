# ====== Code Summary ======
# PreflightCache — a process-wide, short-TTL cache of POSITIVE preflight results, keyed by
# (collection_id, blob_hash). The runner preflights every provider leaf's reachability before EVERY
# run, so a burst of K documents on one warm collection pays K×P live HTTP probes re-proving the same
# reachable endpoints. This cache lets the 2nd..Kth document within the TTL SKIP the probe once the
# first (cold) document proved the collection reachable. The fail-fast-before-spend guarantee is kept:
# ONLY a success is remembered (a failure raises before it is cached, so a recovered endpoint is
# re-probed on the next document rather than stuck failing), the FIRST document of a cold collection
# always probes, and the key carries the blob_hash so any pipeline-config change re-probes. Monotonic
# time (never wall-clock) bounds the TTL so a clock adjustment can neither extend nor shorten it.

# ====== Standard Library Imports ======
import time

# The cache key: the owning collection plus a hash of its pipeline blob (a config change re-probes).
_CacheKey = tuple[str, str]


class PreflightCache:
    """Process-wide registry of fresh POSITIVE preflight results, keyed by (collection_id, blob_hash)."""

    _entries: dict[_CacheKey, float] = {}

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("PreflightCache is a static-only class and cannot be instantiated.")

    @classmethod
    def is_fresh(cls, collection_id: str, blob_hash: str) -> bool:
        """
        Whether a positive preflight for this (collection, blob) is still within its TTL.

        Args:
            collection_id (str): The owning collection id.
            blob_hash (str): The stable hash of the collection's pipeline blob.

        Returns:
            bool: True when a prior success is still fresh (the probe may be skipped); False otherwise.
        """
        expiry = cls._entries.get((collection_id, blob_hash))
        return expiry is not None and expiry > time.monotonic()

    @classmethod
    def remember(cls, collection_id: str, blob_hash: str, ttl_seconds: float) -> None:
        """
        Record a POSITIVE preflight result, fresh for ``ttl_seconds`` from now.

        Called ONLY after a clean sweep (no failures) — a failed preflight raises before reaching here,
        so a down endpoint is never cached and is re-probed on the next document.

        Args:
            collection_id (str): The owning collection id.
            blob_hash (str): The stable hash of the collection's pipeline blob.
            ttl_seconds (float): How long the positive result stays fresh (seconds).
        """
        cls._entries[(collection_id, blob_hash)] = time.monotonic() + ttl_seconds

    @classmethod
    def reset(cls) -> None:
        """Drop every cached result — test isolation / operational flush."""
        cls._entries.clear()


__all__ = ["PreflightCache"]
