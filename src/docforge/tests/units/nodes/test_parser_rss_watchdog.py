"""The parse subprocess' resident-memory watchdog — the default-ON guard against a docling OOM.

Covers the four pieces end to end:

- ``ParseRssWatchdog.wait`` decides reply / timeout / rss from a fake pipe + fake RSS readings
  (fully deterministic, no process);
- the pool KILLS a real forked child whose tree RSS crosses the limit (a scripted RSS reader keeps
  it deterministic; one test also allocates for real with a wide margin) and raises the attributed
  ``ParseMemoryExceededError``, while a child under the limit completes and keeps its warm process;
- ``ProcessTreeHelpers`` counts and kills descendants;
- the default derives from cgroup v2 ``memory.max`` / host RAM and honours an explicit override.
"""

import multiprocessing
import os
import pathlib
import time

import psutil
import pytest

from shared_libs.pipelines.base import NodeConfig
from shared_libs.pipelines.ingest.nodes.parse.parser.docling_base import BaseDoclingParserNode
from shared_libs.pipelines.ingest.nodes.parse.parser.docling_base.subprocess import (
    ContainerMemoryBudget,
    DoclingSubprocessPool,
    MemoryBudget,
    ParseMemoryExceededError,
    ParseRssLimit,
    ParseSubprocessError,
)
from shared_libs.pipelines.ingest.nodes.parse.parser.docling_base.subprocess.process_tree import (
    ProcessTreeHelpers,
)
from shared_libs.pipelines.ingest.nodes.parse.parser.docling_base.subprocess.rss_watchdog import (
    ParseRssWatchdog,
)
from shared_libs.public_models import DocumentIR

pytestmark = pytest.mark.skipif(
    not hasattr(os, "fork"), reason="parse subprocess is fork-based (POSIX)"
)

_MIB = 1024 * 1024
_GIB = 1024 * _MIB


class RssFakeConfig(NodeConfig):
    """Drives the fake convert across the process boundary."""

    mode: str = "ok"
    sleep_s: float = 0.0
    alloc_mb: int = 0


class RssFakeNode:
    """Module-level stand-in for a Docling parser so the forked child can import it by qualname."""

    Config = RssFakeConfig

    def __init__(self, id: str, config: RssFakeConfig) -> None:
        self.id = id
        self.config = config

    def _convert_to_ir(self, content: bytes, suffix: str, source_hash: str) -> DocumentIR:
        """Sleep, or allocate-and-touch ``alloc_mb`` then sleep (runs INSIDE the child)."""
        if self.config.mode == "alloc":
            # Filled (not calloc'd) bytes so every page is really resident.
            hog = b"\x01" * (self.config.alloc_mb * _MIB)
            time.sleep(self.config.sleep_s)
            del hog
        elif self.config.mode == "sleep":
            time.sleep(self.config.sleep_s)
        return DocumentIR(doc_id=source_hash, source_hash=source_hash)


async def _parse(pool: DoclingSubprocessPool, config: RssFakeConfig, **overrides: object):
    kwargs = {
        "node_class": RssFakeNode,
        "config": config,
        "content": b"%PDF-1.4 fake",
        "suffix": ".pdf",
        "source_hash": "hash-1",
        "timeout_seconds": 30.0,
        "memory_mb": 0,
        "rss_limit_mb": 0,
    }
    kwargs.update(overrides)
    return await pool.parse(**kwargs)


def _key() -> tuple[str, int]:
    return (f"{RssFakeNode.__module__}.{RssFakeNode.__qualname__}", 0)


# ==================== ParseRssWatchdog.wait (no process) ====================


class _FakeConn:
    """A pipe whose reply becomes ready after ``ready_after`` polls."""

    def __init__(self, ready_after: int | None) -> None:
        self.polls = 0
        self._ready_after = ready_after

    def poll(self, _timeout: float) -> bool:
        self.polls += 1
        return self._ready_after is not None and self.polls > self._ready_after


class _FakeClock:
    """Advances by each poll slice so deadlines are deterministic."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 0.1
        return self.now


def test_watchdog_fires_when_tree_rss_crosses_the_limit() -> None:
    readings = iter([100 * _MIB, 300 * _MIB, 900 * _MIB])
    watchdog = ParseRssWatchdog(poll_seconds=0, rss_reader=lambda _pid: next(readings))
    outcome = watchdog.wait(_FakeConn(ready_after=None), pid=1, timeout=60, rss_limit_mb=512)
    assert outcome.kind == "rss"
    assert outcome.peak_rss_mb == 900


def test_watchdog_returns_the_reply_when_under_the_limit() -> None:
    watchdog = ParseRssWatchdog(poll_seconds=0, rss_reader=lambda _pid: 100 * _MIB)
    outcome = watchdog.wait(_FakeConn(ready_after=3), pid=1, timeout=60, rss_limit_mb=512)
    assert outcome.kind == "reply"
    assert outcome.peak_rss_mb == 100


def test_watchdog_times_out_on_the_deadline() -> None:
    watchdog = ParseRssWatchdog(poll_seconds=0, rss_reader=lambda _pid: 0, clock=_FakeClock())
    outcome = watchdog.wait(_FakeConn(ready_after=None), pid=1, timeout=1.0, rss_limit_mb=512)
    assert outcome.kind == "timeout"


def test_watchdog_off_never_samples_rss() -> None:
    def _boom(_pid: int) -> int:
        raise AssertionError("RSS must not be read when the watchdog is off")

    watchdog = ParseRssWatchdog(poll_seconds=0, rss_reader=_boom)
    assert (
        watchdog.wait(_FakeConn(ready_after=2), pid=1, timeout=60, rss_limit_mb=0).kind == "reply"
    )


# ==================== the pool's kill path (real forked child) ====================


async def test_pool_kills_a_child_over_the_rss_limit_and_classifies_it() -> None:
    """A scripted reading over the limit SIGKILLs the real child, raises the memory error naming the
    limit + the levers, and the next parse respawns a fresh child."""
    pool = DoclingSubprocessPool()
    pool._watchdog = ParseRssWatchdog(poll_seconds=0.05, rss_reader=lambda _pid: 4 * _GIB)
    try:
        started = time.monotonic()
        with pytest.raises(ParseMemoryExceededError) as excinfo:
            await _parse(pool, RssFakeConfig(mode="sleep", sleep_s=30.0), rss_limit_mb=1024)
        assert time.monotonic() - started < 10  # killed by the watchdog, not the 30 s sleep
        err = excinfo.value
        # Classification: a ParseSubprocessError subtype whose class name is the job's error_type.
        assert isinstance(err, ParseSubprocessError)
        assert type(err).__name__ == "ParseMemoryExceededError"
        message = str(err)
        assert "parse_memory_exceeded" in message
        assert "1024 MiB limit" in message and "4096 MiB" in message
        assert "parse_rss_limit_mb" in message and "WORKER_PARSE_RSS_LIMIT_MB" in message
        assert "do_table_structure off" in message and "split the document" in message
        assert _key() not in pool._children
        pool._watchdog = ParseRssWatchdog(poll_seconds=0.05, rss_reader=lambda _pid: 0)
        ir = await _parse(pool, RssFakeConfig(mode="ok"), rss_limit_mb=1024, source_hash="after")
        assert ir.source_hash == "after"
    finally:
        pool.shutdown()


async def test_pool_kills_a_child_that_really_allocates_past_the_limit() -> None:
    """Real RSS: the child allocates 512 MiB over a limit set 192 MiB above its forked baseline."""
    pool = DoclingSubprocessPool()
    pool._watchdog = ParseRssWatchdog(poll_seconds=0.05)
    limit_mb = psutil.Process().memory_info().rss // _MIB + 192
    try:
        with pytest.raises(ParseMemoryExceededError):
            await _parse(
                pool, RssFakeConfig(mode="alloc", alloc_mb=512, sleep_s=30.0), rss_limit_mb=limit_mb
            )
        assert _key() not in pool._children
    finally:
        pool.shutdown()


async def test_child_under_the_limit_completes_and_stays_warm() -> None:
    pool = DoclingSubprocessPool()
    pool._watchdog = ParseRssWatchdog(poll_seconds=0.05)
    limit_mb = psutil.Process().memory_info().rss // _MIB + 2048
    try:
        ir = await _parse(
            pool, RssFakeConfig(mode="alloc", alloc_mb=32, sleep_s=0.3), rss_limit_mb=limit_mb
        )
        assert ir.source_hash == "hash-1"
        assert _key() in pool._children  # the warm child was NOT killed
    finally:
        pool.shutdown()


# ==================== ProcessTreeHelpers ====================


def _spawn_grandchild(ready: "multiprocessing.Queue") -> None:
    """A child that forks a sleeping grandchild, reports its pid, then sleeps."""
    grand = multiprocessing.get_context("fork").Process(target=time.sleep, args=(60,))
    grand.start()
    ready.put(grand.pid)
    time.sleep(60)


def _dies_within(pid: int, seconds: float) -> bool:
    """True once ``pid`` is gone or a zombie (killed, awaiting its parent's reap)."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if psutil.Process(pid).status() == psutil.STATUS_ZOMBIE:
                return True
        except psutil.NoSuchProcess:
            return True
        time.sleep(0.05)
    return False


def test_process_tree_counts_and_kills_descendants() -> None:
    ctx = multiprocessing.get_context("fork")
    ready: multiprocessing.Queue = ctx.Queue()
    child = ctx.Process(target=_spawn_grandchild, args=(ready,), daemon=False)
    child.start()
    try:
        grand_pid = ready.get(timeout=10)
        child_rss = psutil.Process(child.pid).memory_info().rss
        assert ProcessTreeHelpers.rss_bytes(child.pid) > child_rss  # the grandchild is counted
        ProcessTreeHelpers.kill_descendants(child.pid)
        # The grandchild is its parent's to reap, so "killed" reads as gone or a zombie.
        assert _dies_within(grand_pid, seconds=10)
    finally:
        child.kill()
        child.join(timeout=10)
    assert ProcessTreeHelpers.rss_bytes(child.pid) == 0  # a vanished root reads as 0


# ==================== default derivation ====================


def test_budget_uses_the_cgroup_limit_when_set(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "memory.max"
    path.write_text(f"{4 * _GIB}\n")
    budget = ContainerMemoryBudget.detect(cgroup_memory_max=path, total_ram_bytes=16 * _GIB)
    assert budget == MemoryBudget(total_bytes=4 * _GIB, source="cgroup memory.max")


@pytest.mark.parametrize("content", ["max\n", None, f"{64 * _GIB}"])
def test_budget_falls_back_to_host_ram(tmp_path: pathlib.Path, content: str | None) -> None:
    """Unlimited ("max"), absent, or above-RAM cgroup values all fall back to host RAM."""
    path = tmp_path / "memory.max"
    if content is not None:
        path.write_text(content)
    budget = ContainerMemoryBudget.detect(cgroup_memory_max=path, total_ram_bytes=16 * _GIB)
    assert budget == MemoryBudget(total_bytes=16 * _GIB, source="host RAM")


def test_auto_limit_is_80_percent_minus_the_worker_reserve_with_a_floor() -> None:
    assert ParseRssLimit.auto_mb(MemoryBudget(16 * _GIB, "host RAM")) == 16384 * 8 // 10 - 1024
    # A small container: 0.8*2048-1024 = 614 < floor 50% = 1024.
    assert ParseRssLimit.auto_mb(MemoryBudget(2 * _GIB, "cgroup memory.max")) == 1024


def test_setting_auto_off_and_explicit_override() -> None:
    budget = MemoryBudget(16 * _GIB, "host RAM")
    assert ParseRssLimit.from_setting(-1, budget) == ParseRssLimit.auto_mb(budget)
    assert ParseRssLimit.from_setting(0, budget) == 0
    assert ParseRssLimit.from_setting(6000, budget) == 6000


def test_collection_value_overrides_the_installed_default() -> None:
    try:
        ParseRssLimit.install(8000)
        assert ParseRssLimit.resolve(0) == 8000
        assert ParseRssLimit.resolve(3000) == 3000
        ParseRssLimit.install(0)
        assert ParseRssLimit.resolve(0) == 0
    finally:
        ParseRssLimit.install(0)


def test_every_docling_flavour_exposes_the_rss_knob() -> None:
    """The knob lives on the shared config, so docling AND granite (GPU) both get the watchdog."""
    from shared_libs.pipelines.ingest.nodes.parse.parser.docling_base.config import (
        BaseDoclingParserConfig,
    )

    assert BaseDoclingParserConfig().parse_rss_limit_mb == 0
    for cls in BaseDoclingParserNode.__subclasses__():
        assert "parse_rss_limit_mb" in cls.Config.model_fields
