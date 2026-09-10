# ====== Code Summary ======
# BuildabilityCache — memoizes a collection's ingest-blob BUILDABILITY verdict keyed by a stable hash
# of the stored pipeline blob, so the fleet health/list no longer heals + builds + validates every
# collection's graph on every render. Buildability is a PURE function of the blob and the engine code,
# and the engine code is fixed for the life of the process — so a cache hit is always correct without
# any explicit invalidation: a PATCH changes the blob → a new hash → a recompute, and a code deploy
# restarts the process → a fresh cache. No TTL is needed (the only axis that could flip a verdict for
# an unchanged blob is an engine-code change, which cannot happen in-process).

# ====== Standard Library Imports ======
from collections.abc import Callable

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass


class BuildabilityCache(LoggerClass):
    """In-process cache of ingest-blob buildability, keyed by the blob's stable content hash."""

    def __init__(self) -> None:
        LoggerClass.__init__(self)
        self._verdicts: dict[str, bool] = {}

    def get_or_compute(self, key: str, compute: Callable[[], bool]) -> bool:
        """
        Return the cached buildability for this blob hash, computing + storing it on a miss.

        Args:
            key (str): The stable content hash of the stored pipeline blob.
            compute (Callable[[], bool]): Heals + builds + validates the graph and returns whether it
                is buildable; invoked only on a miss.

        Returns:
            bool: Whether the collection's ingest blob heals, builds and validates.
        """
        # 1. A hit is always correct — buildability is pure over the blob + process-fixed engine.
        if key in self._verdicts:
            return self._verdicts[key]
        # 2. Miss: compute once and memoize for every later list render of this same blob.
        verdict = compute()
        self._verdicts[key] = verdict
        return verdict


__all__ = ["BuildabilityCache"]
