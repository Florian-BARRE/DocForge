# ====== Code Summary ======
# BuiltGraphPool — a per-blob pool of BUILT + VALIDATED search graphs, so the immutable build +
# validate work is paid once per distinct blob instead of on every sub-second search request. A built
# graph is mutable ONLY in its bound read port (``node._capabilities``, set by ``bind()`` and read at
# execute time); the rest is immutable per blob. That single mutable seam is why a built graph cannot
# simply be cached and shared across requests: two concurrent searches on DIFFERENT collections would
# bind their own read ports onto the SAME node objects and the second would leak into the first's run.
# Deep-copying per request is not an option either — the nodes are LoggerClass instances holding the
# non-picklable log sink. So the pool hands each in-flight request its OWN built graph (rebound per
# request) and takes it back on release: sequential requests reuse the one graph, concurrent requests
# transiently build extra graphs. ``acquire``/``release`` never await, so they are atomic under the
# asyncio event loop and need no lock.

# ====== Standard Library Imports ======
from collections.abc import Callable

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import Group

# The per-key cap on idle (released, reusable) graphs. Bounds memory under a burst of concurrency: a
# spike that builds many graphs keeps at most this many warm per blob; the surplus is dropped to GC.
_MAX_IDLE_PER_KEY = 8


class BuiltGraphPool(LoggerClass):
    """Pool of reusable built+validated search graphs, keyed by a stable hash of their blob."""

    def __init__(self, max_idle_per_key: int = _MAX_IDLE_PER_KEY) -> None:
        """
        Args:
            max_idle_per_key (int): Upper bound on idle graphs retained per blob hash.
        """
        LoggerClass.__init__(self)
        self._free: dict[str, list[Group]] = {}
        self._max_idle_per_key = max_idle_per_key

    def acquire(self, key: str, build: Callable[[], Group]) -> Group:
        """
        Check out a built+validated graph for this blob, building one only on a miss.

        The caller OWNS the returned graph until it calls :meth:`release` — it is free to bind a read
        port onto it and execute, with no other request touching the same instance in between.

        Args:
            key (str): The stable blob-hash cache key (same blob → same key → reuse).
            build (Callable[[], Group]): Builds + validates a fresh graph; invoked only on a miss and
                free to raise (an invalid blob) — the pool stores nothing on failure.

        Returns:
            Group: A built, validated, UNBOUND graph the caller owns until release.
        """
        # 1. Reuse a warm graph for this blob — list.pop() is atomic (no await), so a concurrent
        #    acquire can never hand the same instance to two requests.
        free = self._free.get(key)
        if free:
            return free.pop()
        # 2. Miss: build + validate a fresh graph (the callable raises on an invalid blob, un-pooled).
        return build()

    def release(self, key: str, group: Group) -> None:
        """
        Return a graph for reuse once its run has finished (bind + execute done).

        The graph still carries the last run's bound read port; the next acquirer rebinds before
        execution, so that stale reference (a read port holding the shared DB facade + a collection
        id) is overwritten and never read across requests.

        Args:
            key (str): The blob-hash key the graph was acquired under.
            group (Group): The graph to make available again.
        """
        # 1. Keep the graph warm for the next request, bounded so idle graphs can't grow without end.
        free = self._free.setdefault(key, [])
        if len(free) < self._max_idle_per_key:
            free.append(group)


__all__ = ["BuiltGraphPool"]
