"""The killable parse subprocess (DoclingSubprocessPool ↔ child) — the guard for Wave B.

Proves the pool↔child contract WITHOUT importing docling or loading any model: a fake node class whose
``_convert_to_ir`` we drive stands in for a real Docling parser. The child is a REAL forked process
(so SIGKILL / broken-pipe / RLIMIT are exercised for real), and the fake is a module-level class so the
forked child resolves it by (module, qualname) — fork inherits ``sys.modules``, so the test module is
already importable in the child under its stem.

Coverage: happy path (IR round-trips model_dump_json → model_validate_json), TIME cap (SIGKILL +
respawn), a DEAD child (crash → broken pipe + respawn), a genuine convert error (plain RuntimeError,
warm child KEPT), and the MEMORY branch (a real MemoryError over the pipe → "memory" outcome + kill,
plus a real RLIMIT_AS application in a forked child). We deliberately do NOT allocate multi-GB to
trigger the OS OOM-killer — the MemoryError path already crosses the real pipe end-to-end, and the
RLIMIT test proves the cap is really set, so the branch is covered without a flaky giant allocation.
"""

import os
import time

import pytest

from shared_libs.pipelines.base import NodeConfig
from shared_libs.pipelines.ingest.nodes.parse.parser.docling_base.subprocess import (
    DoclingSubprocessPool,
    ParseSubprocessError,
)
from shared_libs.pipelines.ingest.nodes.parse.parser.docling_base.subprocess.child import (
    _apply_memory_cap,
)
from shared_libs.public_models import DocumentIR

# The whole mechanism is POSIX-fork based (the worker only ever runs on Linux).
pytestmark = pytest.mark.skipif(
    not hasattr(os, "fork"), reason="parse subprocess is fork-based (POSIX)"
)


class FakeParseConfig(NodeConfig):
    """Drives the fake convert's behaviour across the process boundary (crosses as a plain dict)."""

    mode: str = "ok"
    sleep_s: float = 0.0


class FakeParseNode:
    """A stand-in for a Docling-family parser: the pool only needs ``Config`` + ``_convert_to_ir``.

    Module-level on purpose so the forked child can import it by (module, qualname).
    """

    Config = FakeParseConfig

    def __init__(self, id: str, config: FakeParseConfig) -> None:
        self.id = id
        self.config = config

    def _convert_to_ir(self, content: bytes, suffix: str, source_hash: str) -> DocumentIR:
        """Simulate a parse outcome selected by the config mode (runs INSIDE the child process)."""
        mode = self.config.mode
        if mode == "sleep":
            time.sleep(self.config.sleep_s)
        elif mode == "crash":
            os._exit(1)  # a hard death mid-parse — the parent must see a broken pipe, not a hang
        elif mode == "raise":
            raise ValueError("bad pdf")
        elif mode == "memory":
            raise MemoryError("simulated RLIMIT_AS cap hit")
        return DocumentIR(doc_id=source_hash, source_hash=source_hash)


def _key(memory_mb: int) -> tuple[str, int]:
    """The pool's child key for the fake node at a given memory budget."""
    return (f"{FakeParseNode.__module__}.{FakeParseNode.__qualname__}", memory_mb)


async def _parse(
    pool: DoclingSubprocessPool, config: FakeParseConfig, **overrides: object
) -> DocumentIR:
    """Run one parse through the pool with sensible test defaults."""
    kwargs = {
        "node_class": FakeParseNode,
        "config": config,
        "content": b"%PDF-1.4 fake",
        "suffix": ".pdf",
        "source_hash": "hash-1",
        "timeout_seconds": 30.0,
        "memory_mb": 0,
    }
    kwargs.update(overrides)
    return await pool.parse(**kwargs)


# ==================== happy path ====================


async def test_happy_parse_returns_the_mapped_ir() -> None:
    """A convert that returns an IR flows back through the pipe as JSON and rehydrates to a DocumentIR."""
    pool = DoclingSubprocessPool()
    try:
        ir = await _parse(pool, FakeParseConfig(mode="ok"), source_hash="abc")
        assert isinstance(ir, DocumentIR)
        assert ir.source_hash == "abc"
    finally:
        pool.shutdown()


# ==================== TIME cap → SIGKILL + respawn ====================


async def test_timeout_kills_the_child_and_respawns_on_the_next_parse() -> None:
    """A convert that hangs past the tiny budget is SIGKILLed (a thread never could be), and the SAME
    key gets a FRESH child on the next parse — the key is not left wedged."""
    pool = DoclingSubprocessPool()
    try:
        with pytest.raises(ParseSubprocessError) as excinfo:
            await _parse(pool, FakeParseConfig(mode="sleep", sleep_s=30.0), timeout_seconds=0.5)
        assert "time" in str(excinfo.value)
        # The killed child was reaped and forgotten — the key no longer holds a process.
        assert _key(0) not in pool._children
        # Respawn: the very next parse on the same key succeeds on a brand-new child.
        ir = await _parse(pool, FakeParseConfig(mode="ok"), source_hash="after-timeout")
        assert ir.source_hash == "after-timeout"
    finally:
        pool.shutdown()


# ==================== DEAD child (crash) → broken pipe + respawn ====================


async def test_dead_child_surfaces_a_crash_error_and_respawns() -> None:
    """A child that dies mid-parse (os._exit) breaks the pipe → an attributed crash failure, then the
    next parse respawns a fresh child."""
    pool = DoclingSubprocessPool()
    try:
        with pytest.raises(ParseSubprocessError) as excinfo:
            await _parse(pool, FakeParseConfig(mode="crash"))
        assert "died" in str(excinfo.value)
        assert _key(0) not in pool._children
        ir = await _parse(pool, FakeParseConfig(mode="ok"), source_hash="after-crash")
        assert ir.source_hash == "after-crash"
    finally:
        pool.shutdown()


# ==================== genuine convert error → plain RuntimeError, warm child KEPT ====================


async def test_convert_error_is_a_plain_runtime_error_and_keeps_the_warm_child() -> None:
    """A real convert failure (a corrupt PDF) is NOT a budget error: it re-raises as a plain
    RuntimeError carrying the cause, and the warm child (with its loaded models) is KEPT for the next
    document."""
    pool = DoclingSubprocessPool()
    try:
        with pytest.raises(RuntimeError) as excinfo:
            await _parse(pool, FakeParseConfig(mode="raise"))
        # Not the isolation/budget failure — the genuine cause is preserved.
        assert not isinstance(excinfo.value, ParseSubprocessError)
        assert "bad pdf" in str(excinfo.value)
        # The child was NOT killed — same live process serves the next parse.
        assert _key(0) in pool._children
        pid_before = pool._children[_key(0)].proc.pid
        ir = await _parse(pool, FakeParseConfig(mode="ok"), source_hash="after-error")
        assert ir.source_hash == "after-error"
        assert pool._children[_key(0)].proc.pid == pid_before
    finally:
        pool.shutdown()


# ==================== MEMORY cap ====================


async def test_memory_error_maps_to_a_budget_failure_and_kills_the_child() -> None:
    """A MemoryError from the child (what the RLIMIT_AS cap raises) crosses the real pipe and maps to
    a "memory" budget failure that KILLS the child (its memory state is reset for the next document)."""
    pool = DoclingSubprocessPool()
    try:
        with pytest.raises(ParseSubprocessError) as excinfo:
            await _parse(pool, FakeParseConfig(mode="memory"), memory_mb=256)
        assert "memory" in str(excinfo.value)
        # Killed after a cap hit → the key is dropped and the next parse respawns fresh.
        assert _key(256) not in pool._children
        ir = await _parse(pool, FakeParseConfig(mode="ok"), memory_mb=256, source_hash="after-oom")
        assert ir.source_hash == "after-oom"
    finally:
        pool.shutdown()


def test_apply_memory_cap_really_sets_rlimit_as_in_a_forked_child() -> None:
    """The child bootstrap applies a real RLIMIT_AS. Verified in a forked child (a large, settable cap
    so a light test process's inherited baseline fits) by reading the limit back — proving the OS-level
    guard is armed, complementing the MemoryError→kill classification above."""
    import multiprocessing
    import resource

    cap_mb = 8192  # well above a light pytest child's virtual footprint, so setrlimit succeeds

    def _child(queue: "multiprocessing.Queue") -> None:
        _apply_memory_cap(cap_mb)
        soft, _hard = resource.getrlimit(resource.RLIMIT_AS)
        queue.put(soft)

    ctx = multiprocessing.get_context("fork")
    queue: multiprocessing.Queue = ctx.Queue()
    proc = ctx.Process(target=_child, args=(queue,))
    proc.start()
    soft = queue.get(timeout=10)
    proc.join(timeout=10)
    assert soft == cap_mb * 1024 * 1024
