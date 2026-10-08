# ====== Code Summary ======
# ParseRssWatchdog — the parent-side wait for a parse child's reply, with the time cap AND a resident-
# memory watchdog folded into one loop. Instead of one blocking ``poll(timeout)``, it polls the pipe in
# short slices; between slices it sums the RSS of the child's whole process tree and reports "rss" the
# moment it crosses the limit, so the pool can SIGKILL the child BEFORE the container's cgroup
# OOM-killer reaps a process at random (possibly the worker itself). It only decides — the pool owns
# the kill + respawn path, shared with the time cap.

# ====== Standard Library Imports ======
import time
from collections.abc import Callable
from dataclasses import dataclass
from multiprocessing.connection import Connection
from typing import Literal

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .process_tree import ProcessTreeHelpers

_MIB = 1024 * 1024

# How often the watchdog samples the child tree's RSS (and re-checks the deadline). Docling allocates
# in page/model-sized steps, so half a second catches a runaway well before it doubles.
DEFAULT_POLL_SECONDS = 0.5


@dataclass(frozen=True, slots=True)
class WatchOutcome:
    """How the wait ended: a reply is ready, the time cap fired, or the RSS limit fired."""

    kind: Literal["reply", "timeout", "rss"]
    peak_rss_mb: int = 0


class ParseRssWatchdog(LoggerClass):
    """Waits for a parse child's reply under a wall-clock deadline and a resident-memory limit."""

    def __init__(
        self,
        poll_seconds: float = DEFAULT_POLL_SECONDS,
        rss_reader: Callable[[int], int] = ProcessTreeHelpers.rss_bytes,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        LoggerClass.__init__(self)
        self._poll_seconds = poll_seconds
        self._rss_reader = rss_reader
        self._clock = clock

    def wait(self, conn: Connection, pid: int, timeout: float, rss_limit_mb: int) -> WatchOutcome:
        """
        Block until the child replies, the deadline passes, or its tree's RSS exceeds the limit.

        Args:
            conn (Connection): The parent end of the child's pipe (a request was already sent).
            pid (int): The parse child's pid (its descendants are counted too).
            timeout (float): Wall-clock cap in seconds for this parse.
            rss_limit_mb (int): Resident-memory limit in MiB for the child tree (0 = no watchdog).

        Returns:
            WatchOutcome: ``reply`` (recv is ready), ``timeout`` or ``rss`` (with the peak seen).
        """
        deadline = self._clock() + timeout
        peak = 0
        while True:
            # 1. Wait one slice for the reply (never past the deadline).
            remaining = deadline - self._clock()
            if remaining <= 0:
                return WatchOutcome(kind="timeout", peak_rss_mb=peak // _MIB)
            if conn.poll(min(self._poll_seconds, remaining)):
                return WatchOutcome(kind="reply", peak_rss_mb=peak // _MIB)
            # 2. No reply yet: sample the tree's resident memory and fire past the limit.
            if rss_limit_mb <= 0:
                continue
            rss = self._rss_reader(pid)
            peak = max(peak, rss)
            if rss > rss_limit_mb * _MIB:
                self.logger.warning(
                    f"Parse subprocess pid={pid} resident memory {rss // _MIB} MiB exceeds its "
                    f"{rss_limit_mb} MiB limit — killing it"
                )
                return WatchOutcome(kind="rss", peak_rss_mb=peak // _MIB)


__all__ = ["DEFAULT_POLL_SECONDS", "ParseRssWatchdog", "WatchOutcome"]
