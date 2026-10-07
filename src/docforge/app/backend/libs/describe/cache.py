# ====== Code Summary ======
# DescribeCache — a small in-process, bounded (LRU) cache of composed collection guides
# (GET /collections/{id}/describe), so repeated agent calls don't re-scan every field's distinct values.
# An entry is served only while (a) the collection's change stamp is unchanged — the stamp moves on
# ingestion, delete, metadata value edit and collection/schema PATCH, from ANY process — and (b) it is
# younger than RUNTIME_CONFIG.DESCRIBE_CACHE_TTL_SECONDS (read live; 0 disables the cache). No lock:
# get/put are synchronous (no await between the dict read and write), so the event loop never
# interleaves them.

# ====== Standard Library Imports ======
import time
import uuid
from collections import OrderedDict
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG

# ====== Local Project Imports ======
from .models import CollectionDescription

# Max collections kept — the guide is a few KB, so this bounds the cache to a few MB at most.
DESCRIBE_CACHE_MAX_ENTRIES = 256


class DescribeCache(LoggerClass):
    """Bounded LRU of collection guides, keyed by collection id and validated by a change stamp."""

    def __init__(self, max_entries: int = DESCRIBE_CACHE_MAX_ENTRIES) -> None:
        """
        Args:
            max_entries (int): The most collections kept; the least recently used is evicted beyond.
        """
        LoggerClass.__init__(self)
        self._max_entries = max_entries
        self._entries: OrderedDict[uuid.UUID, tuple[Any, float, CollectionDescription]] = (
            OrderedDict()
        )

    @staticmethod
    def _ttl() -> float:
        """The live TTL in seconds (read per call so a config override applies at once)."""
        return float(RUNTIME_CONFIG.DESCRIBE_CACHE_TTL_SECONDS)

    def get(self, collection_id: uuid.UUID, stamp: Any) -> CollectionDescription | None:
        """
        Return the cached guide when its stamp still matches and it is within the TTL, else None.

        Args:
            collection_id (uuid.UUID): The collection.
            stamp (Any): The collection's CURRENT change stamp (compared for equality).

        Returns:
            CollectionDescription | None: The cached guide, or None on a miss/stale entry.
        """
        # 1. Disabled, or never cached → miss.
        entry = self._entries.get(collection_id)
        if self._ttl() <= 0 or entry is None:
            return None
        # 2. A moved stamp or an expired entry is dropped (never served).
        cached_stamp, stored_at, description = entry
        if cached_stamp != stamp or time.monotonic() - stored_at > self._ttl():
            del self._entries[collection_id]
            return None
        # 3. Hit → mark most recently used.
        self._entries.move_to_end(collection_id)
        self.logger.debug(f"Describe cache hit for collection {collection_id}")
        return description

    def put(self, collection_id: uuid.UUID, stamp: Any, description: CollectionDescription) -> None:
        """
        Store a freshly composed guide under the stamp read BEFORE it was composed.

        Args:
            collection_id (uuid.UUID): The collection.
            stamp (Any): The change stamp read before composing (a write racing the compose then
                moves the stamp, so the entry is refreshed rather than served stale).
            description (CollectionDescription): The composed guide.
        """
        # 1. Disabled → store nothing.
        if self._ttl() <= 0:
            return
        # 2. Insert as most recently used, then evict the least recently used beyond the bound.
        self._entries[collection_id] = (stamp, time.monotonic(), description)
        self._entries.move_to_end(collection_id)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        """Drop every entry (test isolation)."""
        self._entries.clear()


# The process-wide instance the describe route uses.
DESCRIBE_CACHE = DescribeCache()

__all__ = ["DESCRIBE_CACHE", "DESCRIBE_CACHE_MAX_ENTRIES", "DescribeCache"]
