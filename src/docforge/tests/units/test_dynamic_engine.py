# ====== Code Summary ======
# Unit tests for the dynamic engine loop (AbstractPipeline.run driven by injected EngineHooks).
# All mocked, no infra. Asserts: stages run in topo order; the node fingerprint wrapper uses
# node_type=stage.key + code_version=SPEC.code_version + fingerprint_params + upstream-producer input
# fps; NODE_CACHED stages consult/store the cache and SKIP the run on a hit (from_cache set); the
# collection_id gate (should_run False -> skipped + on_skipped, no run); FAIL_DOC marks the doc
# failed + re-raises; mark_done fires on success. Stages declare a single StageSpec; the node-cache
# keys on the StageKey directly (the legacy "s0"/"s1" NODE_TYPE concept is gone).

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
    StageKey,
    StageSpec,
)
from common_libs.pipeline.bricks.tracking import ExecutionTrace
from common_libs.pipeline.caches.fingerprint import compute_fingerprint
from common_libs.pipeline.stages.context import PipelineContext

# ====== Local Project Imports ======
from .dynamic_step_helpers import RunnerStep


# ─── Test scaffolding ────────────────────────────────────────────────────────────


def _mk_stage(
    log: list[str],
    key: StageKey,
    *,
    after: tuple[StageKey, ...] = (),
    consumes: tuple[str, ...] = (),
    produces: tuple[str, ...] = (),
    cache: CachePolicy = CachePolicy.IDEMPOTENT_WRITE,
    on_error: ErrorPolicy = ErrorPolicy.FAIL_DOC,
    code_version: str = "1.0",
    fail: bool = False,
) -> type[AbstractStage]:
    """Build a concrete recording stage whose single step appends its key to ``log`` (or raises)."""

    spec = StageSpec(
        key=key, name=str(key), description="", after=tuple(after), consumes=tuple(consumes),
        produces=tuple(produces), cache_policy=cache, error_policy=on_error, code_version=code_version,
    )

    async def _run(self: Any, ctx: PipelineContext) -> None:
        if fail:
            raise RuntimeError(f"{key} boom")
        log.append(str(self.key))

    def _init(self: Any) -> None:
        AbstractStage.__init__(self)
        self._steps = [
            RunnerStep(
                key=str(self.key), name=str(self.key), description="",
                consumes=self.consumes, produces=self.produces,
                runner=lambda ctx, _self=self: _run(_self, ctx),
            )
        ]

    namespace: dict[str, Any] = {
        "SPEC": spec,
        "fingerprint_params": lambda self: {"k": str(self.key)},
        "steps": property(lambda self: self._steps),
        "__init__": _init,
    }
    return type(f"_St_{key.value}", (AbstractStage,), namespace)


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
        return stage.key not in self.skip_keys

    async def on_skipped(self, stage: AbstractStage, ctx: PipelineContext) -> None:
        self.skipped.append(str(stage.key))

    async def cache_load(self, stage: AbstractStage, ctx: PipelineContext, fingerprint: str) -> bool:
        self.cache_load_calls.append((str(stage.key), fingerprint))
        return stage.key in self.hit_keys

    async def cache_store(self, stage: AbstractStage, ctx: PipelineContext, fingerprint: str) -> None:
        self.cache_store_calls.append((str(stage.key), fingerprint))

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
        a = _mk_stage(log, StageKey.INGEST, produces=("ra",))
        b = _mk_stage(log, StageKey.PARSE, after=(StageKey.INGEST,), consumes=("ra",), produces=("rb",))
        c = _mk_stage(log, StageKey.ENRICH, after=(StageKey.PARSE,), consumes=("rb",))
        hooks = _RecordingHooks()
        pipeline = _Pipeline([c(), a(), b()], hooks=hooks)  # shuffled -> topo sorts

        await pipeline.run(PipelineContext(source_hash="HASH"))

        assert log == ["ingest", "parse", "enrich"]
        assert hooks.prepared is True
        assert hooks.mark_done_called is True

    @pytest.mark.asyncio
    async def test_fingerprint_wrapper_and_input_chaining(self) -> None:
        log: list[str] = []
        a = _mk_stage(log, StageKey.INGEST, produces=("ra",), cache=CachePolicy.NODE_CACHED, code_version="2.5")
        b = _mk_stage(log, StageKey.PARSE, after=(StageKey.INGEST,), consumes=("ra",), cache=CachePolicy.NODE_CACHED)
        hooks = _RecordingHooks()
        ctx = PipelineContext(source_hash="ROOTHASH")
        pipeline = _Pipeline([a(), b()], hooks=hooks)

        await pipeline.run(ctx)

        # Root stage seeded with the content address; wrapper = node_type(stage.key) + code_version.
        expected_a = compute_fingerprint(
            node_type="ingest", code_version="2.5", params={"k": "ingest"}, input_fingerprints=["ROOTHASH"]
        )
        # 'parse' chains off 'ingest' (consumes a key it produced) -> input = [fingerprint(ingest)].
        expected_b = compute_fingerprint(
            node_type="parse", code_version="1.0", params={"k": "parse"}, input_fingerprints=[expected_a]
        )
        assert ctx.fingerprints[StageKey.INGEST] == expected_a
        assert ctx.fingerprints[StageKey.PARSE] == expected_b
        # The same fingerprints were the cache-load keys.
        assert dict(hooks.cache_load_calls) == {"ingest": expected_a, "parse": expected_b}

    @pytest.mark.asyncio
    async def test_collection_gate_skips_stage(self) -> None:
        log: list[str] = []
        chunk = _mk_stage(log, StageKey.CHUNK, produces=("chunks",))
        embed = _mk_stage(log, StageKey.EMBED_INDEX, after=(StageKey.CHUNK,), consumes=("chunks",))
        hooks = _RecordingHooks(skip_keys={"embed_index"})  # gate says: no collection
        pipeline = _Pipeline([chunk(), embed()], hooks=hooks)

        await pipeline.run(PipelineContext(source_hash="H"))

        assert log == ["chunk"]                  # embed/index never ran
        assert hooks.skipped == ["embed_index"]  # on_skipped fired (PG-only persist in prod)
        assert hooks.mark_done_called is True

    @pytest.mark.asyncio
    async def test_fail_doc_marks_failed_and_reraises(self) -> None:
        log: list[str] = []
        a = _mk_stage(log, StageKey.INGEST, fail=True, on_error=ErrorPolicy.FAIL_DOC)
        hooks = _RecordingHooks()
        pipeline = _Pipeline([a()], hooks=hooks)

        with pytest.raises(RuntimeError):
            await pipeline.run(PipelineContext(source_hash="H"))

        assert hooks.mark_failed_called is True
        assert hooks.mark_done_called is False  # never reached on a fail-closed error

    @pytest.mark.asyncio
    async def test_cache_hit_recorded_in_trace(self) -> None:
        log: list[str] = []
        a = _mk_stage(log, StageKey.INGEST, cache=CachePolicy.NODE_CACHED)
        hooks = _RecordingHooks(hit_keys={"ingest"})
        ctx = PipelineContext(source_hash="H")
        await _Pipeline([a()], hooks=hooks).run(ctx)

        trace = ExecutionTrace.for_context(ctx)
        assert trace.stages[0].key == "ingest"
        assert trace.stages[0].cache_hit is True


# ─── Realistic node-cache double: start->get ORDERING is the regression the pinned mock hid ───


class _FakeNodeCacheHooks(EngineHooks):
    """
    A realistic node-cache double honouring real start/get/store semantics.

    The store is keyed by ``(stage.key, fingerprint)``. ``before_stage`` records the 'running' start
    marker; if the engine ever fired it BEFORE ``cache_load`` (the inversion) a stored 'done' entry
    would be clobbered and the second run would miss — so the call-order assertions are the guard.
    """

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], dict] = {}
        self.calls: list[tuple[str, str]] = []  # (kind, key) in invocation order

    async def before_stage(self, stage: AbstractStage, ctx: PipelineContext) -> None:
        if stage.cache_policy == CachePolicy.NODE_CACHED:
            self.calls.append(("start", str(stage.key)))

    async def cache_load(self, stage: AbstractStage, ctx: PipelineContext, fingerprint: str) -> bool:
        self.calls.append(("get", str(stage.key)))
        if (str(stage.key), fingerprint) in self.store:
            ctx.aux.setdefault("loaded", []).append(str(stage.key))
            return True
        return False

    async def cache_store(self, stage: AbstractStage, ctx: PipelineContext, fingerprint: str) -> None:
        self.calls.append(("store", str(stage.key)))
        self.store[(str(stage.key), fingerprint)] = {"ok": True}


class TestRealisticNodeCacheOrdering:
    """First run misses (get->start->store); the SECOND run with the same fp HITS without start."""

    @pytest.mark.asyncio
    async def test_miss_then_hit_with_correct_ordering(self) -> None:
        log: list[str] = []
        # The node cache keys on the StageKey directly (no separate NODE_TYPE).
        stage_cls = _mk_stage(log, StageKey.INGEST, cache=CachePolicy.NODE_CACHED)
        hooks = _FakeNodeCacheHooks()  # shared store across both runs

        # --- Run 1: cold cache -> MISS -> body runs -> stored. get precedes start (no clobber). ---
        ctx1 = PipelineContext(source_hash="HASH")
        await _Pipeline([stage_cls()], hooks=hooks).run(ctx1)

        assert log == ["ingest"]                      # body ran on the miss
        assert ctx1.from_cache[StageKey.INGEST] is False
        assert hooks.calls == [("get", "ingest"), ("start", "ingest"), ("store", "ingest")]
        # (c) fingerprint keys on the StageKey "ingest".
        expected_fp = compute_fingerprint(
            node_type="ingest", code_version="1.0", params={"k": "ingest"}, input_fingerprints=["HASH"]
        )
        assert ctx1.fingerprints[StageKey.INGEST] == expected_fp
        assert ("ingest", expected_fp) in hooks.store  # stored under the stage key

        # --- Run 2: same fingerprint -> HIT -> body skipped -> start NEVER fired before get. ---
        hooks.calls.clear()
        log.clear()
        ctx2 = PipelineContext(source_hash="HASH")
        await _Pipeline([stage_cls()], hooks=hooks).run(ctx2)

        assert log == []                              # body skipped on the hit
        assert ctx2.from_cache[StageKey.INGEST] is True
        assert ctx2.aux["loaded"] == ["ingest"]       # load_artifact path taken
        assert hooks.calls == [("get", "ingest")]     # ONLY get — no start, no store on a hit
