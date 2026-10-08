# ====== Code Summary ======
# DeclaredVectorsCache — a short-TTL, per-collection cache of what the Qdrant store DECLARES (named
# vectors + IDF modifiers). It lets the target-less default search detect a content sparse vector
# encoded by another sparse provider without paying a Qdrant round-trip on every query: the store's
# declarations only change on an ingest into a fresh space or a rebuild, so a 30 s staleness is
# harmless (a stale entry only delays the lexical-axis drop/restore by that long). The read is
# best-effort: a store error yields None (no correction) and is not cached — the search itself then
# meets the store and surfaces its own typed error, so this guard never turns into a 500.

# ====== Standard Library Imports ======
import time
import uuid
from collections.abc import Awaitable, Callable

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.services.db.qdrant import DeclaredVectors

# How long one store read is reused for the same collection.
DECLARED_TTL_SECONDS = 30.0

DeclaredLoader = Callable[[uuid.UUID], Awaitable[DeclaredVectors | None]]


class DeclaredVectorsCache(LoggerClass):
    """Process-wide TTL cache of a collection's declared vectors (one entry per collection)."""

    def __init__(self, ttl_seconds: float = DECLARED_TTL_SECONDS) -> None:
        """
        Args:
            ttl_seconds (float): How long a store read stays fresh.
        """
        LoggerClass.__init__(self)
        self._ttl = ttl_seconds
        self._entries: dict[uuid.UUID, tuple[float, DeclaredVectors | None]] = {}

    async def get(self, collection_id: uuid.UUID, loader: DeclaredLoader) -> DeclaredVectors | None:
        """
        The collection's declared vectors — cached when fresh, else read through ``loader``.

        Args:
            collection_id (uuid.UUID): The collection whose store is inspected.
            loader (DeclaredLoader): The store read (``index_state.declared``).

        Returns:
            DeclaredVectors | None: The declarations (None = no Qdrant space yet, or the store
                could not be read).
        """
        # 1. A fresh entry is served as is.
        now = time.monotonic()
        entry = self._entries.get(collection_id)
        if entry is not None and now - entry[0] < self._ttl:
            return entry[1]
        # 2. Otherwise one store read, remembered for the TTL (a failed read is not remembered).
        try:
            declared = await loader(collection_id)
        except Exception as exc:
            self.logger.warning(
                f"Declared-vectors read failed for {collection_id} ({type(exc).__name__}) — "
                f"default search runs uncorrected"
            )
            return None
        self._entries[collection_id] = (now, declared)
        return declared


__all__ = ["DeclaredVectorsCache", "DECLARED_TTL_SECONDS"]
