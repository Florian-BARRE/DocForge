# ====== Code Summary ======
# Unit tests for the PR-3 dynamic engine loop (AbstractPipeline.run driven by injected EngineHooks).
# All mocked, no infra. Asserts: stages run in topo order; the node fingerprint wrapper uses
# node_type=KEY + code_version=NODE_VERSION + fingerprint_params + upstream-producer input fps;
# NODE_CACHED stages consult/store the cache and SKIP the run on a hit (from_cache set); the
# collection_id gate (should_run False -> skipped + on_skipped, no run); ON_ERROR=FAIL_DOC marks
# the doc failed + re-raises; mark_done fires on success.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from common_libs.pipeline.base import (
    AbstractPipeline,
    AbstractStage,
    CachePolicy,
    EngineHooks,
    ErrorPolicy,
)
from common_libs.pipeline.bricks.tracking import ExecutionTrace
from common_libs.pipeline.caches.fingerprint import compute_fingerprint
from common_libs.pipeline.stages.context import PipelineContext

# ====== Local Project Imports ======
from .dynamic_step_helpers import RunnerStep


# ─── Test scaffolding ────────────────────────────────────────────────────────────


def _mk_stage(
    log: list[str],
    key: str,
    *,
    after: tuple[str, ...] = (),
    consumes: tuple[str, ...] = (),
    produces: tuple[str, ...] = (),
    cache: CachePolicy = CachePolicy.IDEMPOTENT_WRITE,
    on_error: ErrorPolicy = ErrorPolicy.FAIL_DOC,
    node_version: str = "1.0",
    node_type: str = "",
    fail: bool = False,
) -> type[AbstractStage]:
    """Build a concrete recording stage whose single step appends its KEY to ``log`` (or raises)."""

    async def _run(self: Any, ctx: PipelineContext) -> None:
        if fail:
            raise RuntimeError(f"{key} boom")
        log.append(self.KEY)

    def _init(self: Any) -> None:
        AbstractStage.__init__(self)
        self._steps = [
            RunnerStep(
                key=self.KEY, name=self.NAME, description="",
                consumes=self.CONSUMES, produces=self.PRODUCES,
                runner=lambda ctx, _self=self: _run(_self, ctx),
            )
        ]

    namespace: dict[str, Any] = {
        "KEY": key,
        "NAME": key,
        "DESCRIPTION": "",
        "AFTER": tuple(after),
        "CONFIG": None,
        "CONSUMES": tuple(consumes),
        "PRODUCES": tuple(produces),
        "CACHE_POLICY": cache,
        "ON_ERROR": on_error,
        "NODE_VERSION": node_version,
        "NODE_TYPE": node_type,
        "fingerprint_params": lambda self: {"k": self.KEY},
        "steps": property(lambda self: self._steps),
        "__init__": _init,
    }
    return type(f"_St_{key}", (AbstractStage,), namespace)


class _Pipeline(AbstractPipeline):
    """Concrete pipeline used to drive the engine loop in tests."""

    KEY = "test"
    NAME = "Test"


class _RecordingHooks(EngineHooks):
    """Records every hook invocation and lets a test pin cache hits / skip gates."""

    def __init__(self, *, hit_keys: set[str] | None = None, skip_keys: set[str] | None = None) -> None:
        self.hit_keys = hit_keys or set()
        self.skip_keys = skip_keys or set()
        self.cache_load_calls: list[tuple[str, str]] = []
        self.cache_store_calls: list[tuple[str, str]] = []
        self.skipped: list[str] = []
        self.mark_failed_called = False
        self.mark_done_called = False
        self.prepared = False

    async def prepare(self, ctx: PipelineContext) -> None:
        self.prepared = True

    async def should_run(self, stage: AbstractStage, ctx: PipelineContext) -> bool:
        return stage.KEY not in self.skip_keys

    async def on_skipped(self, stage: AbstractStage, ctx: PipelineContext) -> None:
        self.skipped.append(stage.KEY)

    async def cache_load(self, stage: AbstractStage, ctx: PipelineContext, fingerprint: str) -> bool:
        self.cache_load_calls.append((stage.KEY, fingerprint))
        return stage.KEY in self.hit_keys

    async def cache_store(self, stage: AbstractStage, ctx: PipelineContext, fingerprint: str) -> None:
        self.cache_store_calls.append((stage.KEY, fingerprint))

    async def mark_failed(self, ctx: PipelineContext) -> None:
        self.mark_failed_called = True

    async def mark_done(self, ctx: PipelineContext) -> None:
        self.mark_done_called = True


# ─── Tests ─────────────────────────────────────────────────────────────────────


class TestDynamicEngineLoop:
    """AbstractPipeline.run drives stages with fingerprint + cache + gate + ON_ERROR + lifecycle."""

    @pytest.mark.asyncio
    async def test_runs_in_topo_order_and_marks_done(self) -> None:
        log: list[str] = []
        a = _mk_stage(log, "a", produces=("ra",))
        b = _mk_stage(log, "b", after=("a",), consumes=("ra",), produces=("rb",))
        c = _mk_stage(log, "c", after=("b",), consumes=("rb",))
        hooks = _RecordingHooks()
        pipeline = _Pipeline([c(), a(), b()], hooks=hooks)  # shuffled -> topo sorts

        await pipeline.run(PipelineContext(source_hash="HASH"))

        assert log == ["a", "b", "c"]
        assert hooks.prepared is True
        assert hooks.mark_done_called is True

    @pytest.mark.asyncio
    async def test_fingerprint_wrapper_and_input_chaining(self) -> None:
        log: list[str] = []
        a = _mk_stage(log, "a", produces=("ra",), cache=CachePolicy.NODE_CACHED, node_version="2.5")
        b = _mk_stage(log, "b", after=("a",), consumes=("ra",), cache=CachePolicy.NODE_CACHED)
        hooks = _RecordingHooks()
        ctx = PipelineContext(source_hash="ROOTHASH")
        pipeline = _Pipeline([a(), b()], hooks=hooks)

        await pipeline.run(ctx)

        # Root stage 'a' is seeded with the content address; wrapper = node_type/KEY + NODE_VERSION.
        expected_a = compute_fingerprint(
            node_type="a", code_version="2.5", params={"k": "a"}, input_fingerprints=["ROOTHASH"]
        )
        # 'b' chains off 'a' (consumes a key 'a' produced) -> input = [fingerprint(a)].
        expected_b = compute_fingerprint(
            node_type="b", code_version="1.0", params={"k": "b"}, input_fingerprints=[expected_a]
        )
        assert ctx.fingerprints["a"] == expected_a
        assert ctx.fingerprints["b"] == expected_b
        # The same fingerprints were the cache-load keys.
        assert dict(hooks.cache_load_calls) == {"a": expected_a, "b": expected_b}

    @pytest.mark.asyncio
    async def test_collection_gate_skips_stage(self) -> None:
        log: list[str] = []
        chunk = _mk_stage(log, "chunk", produces=("chunks",))
        embed = _mk_stage(log, "embed_index", after=("chunk",), consumes=("chunks",))
        hooks = _RecordingHooks(skip_keys={"embed_index"})  # gate says: no collection
        pipeline = _Pipeline([chunk(), embed()], hooks=hooks)

        await pipeline.run(PipelineContext(source_hash="H"))

        assert log == ["chunk"]                 # embed/index never ran
        assert hooks.skipped == ["embed_index"]  # on_skipped fired (PG-only persist in prod)
        assert hooks.mark_done_called is True

    @pytest.mark.asyncio
    async def test_fail_doc_marks_failed_and_reraises(self) -> None:
        log: list[str] = []
        a = _mk_stage(log, "a", fail=True, on_error=ErrorPolicy.FAIL_DOC)
        hooks = _RecordingHooks()
        pipeline = _Pipeline([a()], hooks=hooks)

        with pytest.raises(RuntimeError):
            await pipeline.run(PipelineContext(source_hash="H"))

        assert hooks.mark_failed_called is True
        assert hooks.mark_done_called is False  # never reached on a fail-closed error

    @pytest.mark.asyncio
    async def test_cache_hit_recorded_in_trace(self) -> None:
        log: list[str] = []
        a = _mk_stage(log, "a", cache=CachePolicy.NODE_CACHED)
        hooks = _RecordingHooks(hit_keys={"a"})
        ctx = PipelineContext(source_hash="H")
        await _Pipeline([a()], hooks=hooks).run(ctx)

        trace = ExecutionTrace.for_context(ctx)
        assert trace.stages[0].key == "a"
        assert trace.stages[0].cache_hit is True


# ─── Realistic node-cache double: start->get ORDERING is the regression the pinned mock hid ───


class _FakeNodeCacheHooks(EngineHooks):
    """
    A realistic node-cache double honouring real start/get/store semantics.

    The store is keyed by ``(node_type, fingerprint)`` (the legacy id, not the KEY). ``before_stage``
    records the 'running' start marker; if the engine ever fired it BEFORE ``cache_load`` (the
    BLOCKING-1 inversion) a stored 'done' entry would be clobbered and the second run would miss —
    so the call-order assertions below are the regression guard.
    """

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], dict] = {}
        self.calls: list[tuple[str, str]] = []  # (kind, node_type) in invocation order

    async def before_stage(self, stage: AbstractStage, ctx: PipelineContext) -> None:
        if stage.CACHE_POLICY == CachePolicy.NODE_CACHED:
            self.calls.append(("start", stage.node_type))

    async def cache_load(self, stage: AbstractStage, ctx: PipelineContext, fingerprint: str) -> bool:
        self.calls.append(("get", stage.node_type))
        if (stage.node_type, fingerprint) in self.store:
            ctx.aux.setdefault("loaded", []).append(stage.node_type)
            return True
        return False

    async def cache_store(self, stage: AbstractStage, ctx: PipelineContext, fingerprint: str) -> None:
        self.calls.append(("store", stage.node_type))
        self.store[(stage.node_type, fingerprint)] = {"ok": True}


class TestRealisticNodeCacheOrdering:
    """First run misses (get->start->store); the SECOND run with the same fp HITS without start."""

    @pytest.mark.asyncio
    async def test_miss_then_hit_with_correct_ordering_and_node_type(self) -> None:
        log: list[str] = []
        # KEY 'ingest' but legacy NODE_TYPE 's0' — the cache must key on the node_type.
        stage_cls = _mk_stage(log, "ingest", cache=CachePolicy.NODE_CACHED, node_type="s0")
        hooks = _FakeNodeCacheHooks()  # shared store across both runs

        # --- Run 1: cold cache -> MISS -> body runs -> stored. get precedes start (no clobber). ---
        ctx1 = PipelineContext(source_hash="HASH")
        await _Pipeline([stage_cls()], hooks=hooks).run(ctx1)

        assert log == ["ingest"]                      # body ran on the miss
        assert ctx1.from_cache["ingest"] is False
        assert hooks.calls == [("get", "s0"), ("start", "s0"), ("store", "s0")]
        # (c) fingerprint uses NODE_TYPE "s0" (not the KEY "ingest").
        expected_fp = compute_fingerprint(
            node_type="s0", code_version="1.0", params={"k": "ingest"}, input_fingerprints=["HASH"]
        )
        assert ctx1.fingerprints["ingest"] == expected_fp
        assert ("s0", expected_fp) in hooks.store     # stored under the legacy node_type

        # --- Run 2: same fingerprint -> HIT -> body skipped -> start NEVER fired before get. ---
        hooks.calls.clear()
        log.clear()
        ctx2 = PipelineContext(source_hash="HASH")
        await _Pipeline([stage_cls()], hooks=hooks).run(ctx2)

        assert log == []                              # body skipped on the hit
        assert ctx2.from_cache["ingest"] is True
        assert ctx2.aux["loaded"] == ["s0"]           # load_artifact path taken
        assert hooks.calls == [("get", "s0")]         # ONLY get — no start, no store on a hit
