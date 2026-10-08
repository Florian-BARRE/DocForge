# ====== Code Summary ======
# DoclingSubprocessPool — the PARENT side of the killable parse. It keeps one WARM, respawnable child
# process per (node class, memory cap) so the heavy docling/granite models load once and amortise
# across documents, and it turns the two failure modes a worker THREAD could never survive into clean,
# attributed job failures: a parse past its TIME limit is SIGKILLed and respawned; a child that OOMs
# or crashes is detected (broken pipe) and respawned. One request per child at a time (an asyncio.Lock
# per key) preserves the old process-wide convert serialisation, now as a process boundary that CAN be
# killed — so one pathological document can never wedge the worker or deadlock a shared convert lock.
# While it waits for a reply, a resident-memory watchdog (ParseRssWatchdog) samples the child tree's
# RSS and SIGKILLs it past the limit through the SAME kill path as the time cap, so a document too
# heavy for the container fails attributed (ParseMemoryExceededError) instead of meeting the cgroup
# OOM-killer.

# ====== Standard Library Imports ======
import asyncio
import atexit
import multiprocessing
from dataclasses import dataclass
from multiprocessing.connection import Connection
from multiprocessing.context import BaseContext
from multiprocessing.process import BaseProcess
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.public_models import DocumentIR

# ====== Local Project Imports ======
from .child import serve
from .errors import ParseMemoryExceededError, ParseSubprocessError
from .failure_messages import ParseFailureMessages
from .process_tree import ProcessTreeHelpers
from .rss_watchdog import ParseRssWatchdog

# How long to wait for a killed/dead child to be reaped before moving on — a SIGKILLed process exits
# promptly; the bounded join just keeps a pathological zombie from blocking the next parse forever.
_REAP_TIMEOUT_SECONDS = 5.0


@dataclass(slots=True)
class _ParseChild:
    """A live warm parse child: its process handle + the parent end of the duplex pipe."""

    proc: BaseProcess
    conn: Connection


class DoclingSubprocessPool(LoggerClass):
    """Process-wide manager of warm, killable parse children (one per node class + memory cap).

    A single shared instance (``instance()``) is used by every Docling-family parser node. It is the
    ONLY place that knows a parse runs out-of-process: the node hands it the class + config + bytes and
    gets the mapped IR back, or a typed failure when the isolated child blew its limit or died.
    """

    _instance: "DoclingSubprocessPool | None" = None

    def __init__(self) -> None:
        LoggerClass.__init__(self)
        # Fork (not spawn) so the child inherits the worker's `shared_libs` import alias + sys.path with
        # zero re-bootstrap, and its OWN CUDA context is created lazily inside the child on first use.
        # Safe here specifically because the PARENT never initialises CUDA (docling/torch are lazy-
        # imported only inside the child), so there is no live CUDA state to corrupt across the fork.
        self._ctx: BaseContext = multiprocessing.get_context("fork")
        self._children: dict[tuple[str, int], _ParseChild] = {}
        self._locks: dict[tuple[str, int], asyncio.Lock] = {}
        self._watchdog = ParseRssWatchdog()
        atexit.register(self.shutdown)

    @classmethod
    def instance(cls) -> "DoclingSubprocessPool":
        """Return the process-wide pool, building it on first use."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __spawn(self, key: tuple[str, int], memory_mb: int) -> _ParseChild:
        """Fork a fresh warm child for a key and register it (models load lazily on its first parse)."""
        parent_conn, child_conn = self._ctx.Pipe(duplex=True)
        proc = self._ctx.Process(target=serve, args=(child_conn, memory_mb), daemon=True)
        proc.start()
        # Drop the parent's copy of the child end so a recv sees EOF the moment the child dies.
        child_conn.close()
        child = _ParseChild(proc=proc, conn=parent_conn)
        self._children[key] = child
        self.logger.info(
            f"Forked parse subprocess for {key[0]} (memory_mb={memory_mb}, pid={proc.pid})"
        )
        return child

    def __kill(self, key: tuple[str, int]) -> None:
        """SIGKILL + reap the child (and any process it spawned) for a key and forget it, so the next
        parse respawns a fresh one."""
        child = self._children.pop(key, None)
        if child is None:
            return
        try:
            # Descendants first: once the child dies they are re-parented and no longer findable.
            if child.proc.pid is not None:
                ProcessTreeHelpers.kill_descendants(child.proc.pid)
            child.proc.kill()
            child.proc.join(timeout=_REAP_TIMEOUT_SECONDS)
        except Exception as exc:  # pragma: no cover - best-effort reap
            self.logger.warning(f"Reaping parse subprocess {key[0]} raised: {exc}")
        try:
            child.conn.close()
        except Exception:  # pragma: no cover - best-effort close
            pass

    def __ensure_child(self, key: tuple[str, int], memory_mb: int) -> _ParseChild:
        """Return a LIVE child for the key, respawning a fresh one if none exists or it has died."""
        child = self._children.get(key)
        if child is not None and child.proc.is_alive():
            return child
        if child is not None:
            self.__kill(key)
        return self.__spawn(key, memory_mb)

    def __run_once(
        self,
        key: tuple[str, int],
        memory_mb: int,
        request: dict[str, Any],
        timeout: float,
        rss_limit_mb: int,
    ) -> tuple[str, Any]:
        """Send ONE request to the key's warm child and classify the outcome (blocking — off-loop).

        Returns a ``(outcome, payload)`` pair the async caller maps to an IR or a typed error:
        ``ok`` (IR JSON), ``timeout`` / ``rss`` / ``dead`` / ``memory`` (the child was killed + will
        respawn), or ``err`` (a genuine convert failure — the warm child survives for the next one).
        """
        child = self.__ensure_child(key, memory_mb)
        # 1. Send the request, then wait UP TO the time limit for a reply while the watchdog samples
        #    the child tree's RSS. A child that hangs past the deadline or grows past the RSS limit is
        #    SIGKILLed here — a thread never could be — so the worker slot (and its memory) is freed.
        try:
            child.conn.send(request)
            outcome = self._watchdog.wait(child.conn, child.proc.pid or 0, timeout, rss_limit_mb)
            if outcome.kind != "reply":
                self.__kill(key)
                return outcome.kind, outcome.peak_rss_mb
            response = child.conn.recv()
        except (EOFError, BrokenPipeError, OSError):
            # The child died mid-parse (an OOM-kill or a native crash) — the pipe broke. Reap + respawn.
            self.__kill(key)
            return "dead", None

        # 2. A successful parse hands the IR back as JSON.
        if response[0] == "ok":
            return "ok", response[1]

        # 3. A reported error: a MemoryError means the cap fired — kill the child so its memory state
        #    resets before the next document; any other error is a normal convert failure (bad PDF)
        #    and the warm child is kept.
        err_type, message = response[1], response[2]
        if err_type == "MemoryError":
            self.__kill(key)
            return "memory", message
        return "err", (err_type, message)

    async def parse(
        self,
        node_class: type,
        config: Any,
        content: bytes,
        suffix: str,
        source_hash: str,
        timeout_seconds: float,
        memory_mb: int,
        rss_limit_mb: int = 0,
    ) -> DocumentIR:
        """Parse ``content`` in the key's warm child and return the mapped IR, or raise a typed failure.

        Args:
            node_class (type): The concrete Docling-family node class (identifies the child + its cache).
            config (Any): The node's NodeConfig (crosses to the child as a plain dict).
            content (bytes): The PDF (or native html/md) bytes to parse.
            suffix (str): The temp-file extension the child writes the bytes under.
            source_hash (str): The IR document id / source hash.
            timeout_seconds (float): Wall-clock cap for THIS parse; the child is killed past it.
            memory_mb (int): The child's address-space cap in MiB (0 disables it).
            rss_limit_mb (int): The resident-memory limit in MiB the parent's watchdog enforces on
                the child tree (0 disables it).

        Returns:
            DocumentIR: The parsed IR.

        Raises:
            ParseMemoryExceededError: The parse crossed its RSS limit or its RLIMIT_AS cap.
            ParseSubprocessError: The parse exceeded its time limit or its subprocess died.
            RuntimeError: A genuine convert failure (its chained docling cause preserved in the message).
        """
        key = (f"{node_class.__module__}.{node_class.__qualname__}", int(memory_mb))
        request = {
            "module": node_class.__module__,
            "qualname": node_class.__qualname__,
            "config": config.model_dump(),
            "content": content,
            "suffix": suffix,
            "source_hash": source_hash,
        }
        # One in-flight parse per child (the old process-wide convert serialisation, per key now).
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            outcome, payload = await asyncio.to_thread(
                self.__run_once,
                key,
                int(memory_mb),
                request,
                timeout_seconds,
                int(rss_limit_mb),
            )

        if outcome == "ok":
            return DocumentIR.model_validate_json(payload)
        if outcome == "timeout":
            raise ParseSubprocessError(ParseFailureMessages.timeout(timeout_seconds))
        if outcome == "rss":
            raise ParseMemoryExceededError(
                ParseFailureMessages.rss_exceeded(int(rss_limit_mb), payload)
            )
        if outcome == "memory":
            raise ParseMemoryExceededError(
                ParseFailureMessages.address_space_exceeded(int(memory_mb), payload)
            )
        if outcome == "dead":
            raise ParseSubprocessError(
                ParseFailureMessages.crashed(timeout_seconds, int(rss_limit_mb))
            )
        # A genuine convert failure — re-raise as a plain RuntimeError so its chained cause still names
        # the real error (e.g. a corrupt PDF), never masked as a limit failure.
        _err_type, message = payload
        raise RuntimeError(message)

    def shutdown(self) -> None:
        """Kill and reap every warm child (registered atexit; also callable on worker teardown)."""
        for key in list(self._children):
            self.__kill(key)


__all__ = ["DoclingSubprocessPool"]
