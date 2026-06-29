# ====== Code Summary ======
# Unit tests for the PR-1 dynamic-pipeline contracts (Pipeline -> Stage -> Step), all mocked.
# Covers: ErrorPolicy/CachePolicy enums; AbstractStage.__init_subclass__ ClassVar enforcement;
# the recursive describe() shape (PipelineSchema/StageSchema/StepSchema); ChainStep describe()
# (provider category + choices) + run() + trace hooks; the ExecutionTrace hierarchical collector;
# topological ordering; and ON_ERROR dispatch (FAIL_DOC propagates, SKIP continues).
# These contracts are additive + UNWIRED — nothing here exercises the production worker path.

# ====== Standard Library Imports ======
from unittest.mock import AsyncMock, MagicMock

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from common_libs.pipeline.base import (
    AbstractPipeline,
    AbstractStage,
    AbstractStep,
    CachePolicy,
    ChainStep,
    ErrorPolicy,
    PipelineSchema,
    StageSchema,
    StepSchema,
)
from common_libs.pipeline.bricks.tracking import ExecutionTrace, StageTrace, StepTrace
from common_libs.pipeline.stages.context import PipelineContext, StageDeps
from common_libs.pipeline.bricks.chain import ChainAttempt, ChainOutcome

# ====== Local Project Imports ======
from .dynamic_step_helpers import RunnerStep


# ─── Minimal concrete stages used across the contract tests ──────────────────────


class _OkStage(AbstractStage):
    """A trivial single-step stage that records a flag on the context aux."""

    KEY = "ok"
    NAME = "Ok"
    DESCRIPTION = "records a flag"
    AFTER: tuple[str, ...] = ()
    CONFIG = None
    CONSUMES: tuple[str, ...] = ()
    PRODUCES: tuple[str, ...] = ("ok",)
    CACHE_POLICY = CachePolicy.NODE_CACHED
    ON_ERROR = ErrorPolicy.FAIL_DOC

    def __init__(self) -> None:
        AbstractStage.__init__(self)
        self._steps = [
            RunnerStep(
                key="ok", name="Ok", description="", consumes=(), produces=("ok",), runner=self._do
            )
        ]

    @property
    def steps(self):
        return self._steps

    async def _do(self, ctx: PipelineContext) -> None:
        ctx.aux["ok"] = True


class _FailFailDocStage(AbstractStage):
    """A stage whose step raises; ON_ERROR=FAIL_DOC → the pipeline must propagate."""

    KEY = "boom_fail"
    NAME = "BoomFail"
    DESCRIPTION = "always raises"
    AFTER: tuple[str, ...] = ()
    CONFIG = None
    CONSUMES: tuple[str, ...] = ()
    PRODUCES: tuple[str, ...] = ()
    CACHE_POLICY = CachePolicy.NODE_CACHED
    ON_ERROR = ErrorPolicy.FAIL_DOC

    def __init__(self) -> None:
        AbstractStage.__init__(self)
        self._steps = [
            RunnerStep(key="b", name="B", description="", consumes=(), produces=(), runner=self._do)
        ]

    @property
    def steps(self):
        return self._steps

    async def _do(self, ctx: PipelineContext) -> None:
        raise RuntimeError("kaboom")


class _FailSkipStage(_FailFailDocStage):
    """Same failing body, but ON_ERROR=SKIP → the pipeline must continue."""

    KEY = "boom_skip"
    NAME = "BoomSkip"
    ON_ERROR = ErrorPolicy.SKIP


class _OkPipeline(AbstractPipeline):
    """A concrete pipeline used to exercise the engine logic."""

    KEY = "test_pipeline"
    NAME = "Test Pipeline"
    DESCRIPTION = "contract test pipeline"


# An intermediate abstract base must NOT trigger ClassVar enforcement (abstract=True).
class _AbstractIntermediate(AbstractStage, abstract=True):
    """Specialises the contract without being runnable — must import without raising."""


# ─── ErrorPolicy / CachePolicy enums ─────────────────────────────────────────────


class TestPolicyEnums:
    """The declarative stage policy enums expose the agreed members + string values."""

    def test_error_policy_members(self) -> None:
        assert ErrorPolicy.FAIL_DOC.value == "fail_doc"
        assert ErrorPolicy.SKIP.value == "skip"
        assert ErrorPolicy.DEGRADE.value == "degrade"
        assert {p.value for p in ErrorPolicy} == {"fail_doc", "skip", "degrade"}

    def test_cache_policy_members(self) -> None:
        assert CachePolicy.NODE_CACHED.value == "node_cached"
        assert CachePolicy.IDEMPOTENT_WRITE.value == "idempotent_write"
        assert {p.value for p in CachePolicy} == {"node_cached", "idempotent_write"}


# ─── __init_subclass__ ClassVar enforcement ──────────────────────────────────────


class TestStageClassVarEnforcement:
    """A concrete AbstractStage must declare every forced ClassVar."""

    def test_missing_classvar_raises(self) -> None:
        with pytest.raises(TypeError) as exc_info:

            class _Bad(AbstractStage):
                KEY = "bad"
                NAME = "Bad"
                DESCRIPTION = "missing ON_ERROR"
                AFTER: tuple[str, ...] = ()
                CONFIG = None
                CONSUMES: tuple[str, ...] = ()
                PRODUCES: tuple[str, ...] = ()
                CACHE_POLICY = CachePolicy.NODE_CACHED
                # ON_ERROR intentionally omitted

                @property
                def steps(self):
                    return []

        assert "ON_ERROR" in str(exc_info.value)

    def test_complete_subclass_is_accepted(self) -> None:
        # _OkStage was defined at import time — its mere existence proves a complete
        # subclass passes enforcement; confirm it instantiates and exposes one step.
        stage = _OkStage()
        assert len(stage.steps) == 1

    def test_abstract_intermediate_skips_enforcement(self) -> None:
        # Defined at module import with abstract=True and no ClassVars; importing this
        # module would have failed if enforcement had fired on it.
        assert issubclass(_AbstractIntermediate, AbstractStage)


# ─── describe(): recursive schema shape ──────────────────────────────────────────


class TestDescribeShapes:
    """describe() emits the recursive PipelineSchema -> StageSchema -> StepSchema tree."""

    def test_stage_describe_shape(self) -> None:
        schema = _OkStage().describe()
        assert isinstance(schema, StageSchema)
        assert schema.key == "ok"
        assert schema.name == "Ok"
        assert schema.cache_policy == CachePolicy.NODE_CACHED
        assert schema.on_error == ErrorPolicy.FAIL_DOC
        assert schema.produces == ["ok"]
        assert len(schema.steps) == 1
        assert isinstance(schema.steps[0], StepSchema)
        assert schema.steps[0].kind == "step"
        assert schema.steps[0].key == "ok"

    def test_step_describe_shape(self) -> None:
        step = RunnerStep(
            key="s", name="S", description="d", consumes=("a",), produces=("b",), runner=AsyncMock()
        )
        schema = step.describe()
        assert isinstance(schema, StepSchema)
        assert schema.kind == "step"
        assert schema.consumes == ["a"]
        assert schema.produces == ["b"]
        assert schema.category is None
        assert schema.providers == []

    def test_pipeline_describe_recurses_in_topo_order(self) -> None:
        # Pass stages out of dependency order to prove topological sorting in describe().
        first = _OkStage()

        class _SecondStage(_OkStage):
            KEY = "ok2"
            NAME = "Ok2"
            AFTER = ("ok",)

        second = _SecondStage()
        pipeline = _OkPipeline([second, first])
        schema = pipeline.describe()
        assert isinstance(schema, PipelineSchema)
        assert schema.key == "test_pipeline"
        assert [s.key for s in schema.stages] == ["ok", "ok2"]


# ─── ChainStep: describe (category + choices), run, trace hooks ──────────────────


class TestChainStep:
    """ChainStep emits its provider category + choices and surfaces chain lineage."""

    def _make_chain(self) -> MagicMock:
        provider = MagicMock()
        provider.name = "bge_m3"
        chain = MagicMock()
        chain.providers = [provider]
        chain.signature = MagicMock(return_value="bge_m3:1")
        return chain

    def test_chain_step_describe_emits_category_and_providers(self) -> None:
        step = ChainStep(
            key="embed",
            name="Embed",
            description="embed the chunk body",
            category="embed",
            chain=self._make_chain(),
            call_builder=lambda ctx: (lambda p: None),
            writer=lambda ctx, outcome: None,
            consumes=("chunks",),
            produces=("vectors",),
        )
        schema = step.describe()
        assert schema.kind == "chain"
        assert schema.category == "embed"
        assert schema.providers == ["bge_m3"]
        assert schema.consumes == ["chunks"]

    def test_chain_step_fingerprint_params_uses_signature(self) -> None:
        step = ChainStep(
            key="embed", name="Embed", description="", category="embed", chain=self._make_chain(),
            call_builder=lambda ctx: (lambda p: None), writer=lambda ctx, o: None,
        )
        assert step.fingerprint_params() == {"chain": "bge_m3:1"}

    @pytest.mark.asyncio
    async def test_chain_step_run_executes_chain_and_writer(self) -> None:
        chain = self._make_chain()
        attempt = ChainAttempt(
            provider_id="bge_m3", score=0.9, duration_ms=4, succeeded=True, escalated=False
        )
        outcome = ChainOutcome(result=[[0.1]], attempts=[attempt], final_provider="bge_m3")
        chain.call = AsyncMock(return_value=outcome)

        written: dict[str, object] = {}

        step = ChainStep(
            key="embed", name="Embed", description="", category="embed", chain=chain,
            call_builder=lambda ctx: (lambda p: None),
            writer=lambda ctx, o: written.__setitem__("result", o.result),
        )
        ctx = PipelineContext()
        await step.run(ctx)

        chain.call.assert_awaited_once()
        assert written["result"] == [[0.1]]
        # Trace hooks surface the chain lineage to the tracking layer.
        assert step.trace_final_provider() == "bge_m3"
        assert step.trace_attempts() == [attempt]


# ─── ExecutionTrace: hierarchical accumulation ───────────────────────────────────


class TestExecutionTrace:
    """A stage run records a hierarchical pipeline -> stage -> step trace entry."""

    @pytest.mark.asyncio
    async def test_stage_run_records_stage_and_step_trace(self) -> None:
        ctx = PipelineContext()
        await _OkStage().run(ctx)

        trace = ExecutionTrace.for_context(ctx)
        assert isinstance(trace, ExecutionTrace)
        assert len(trace.stages) == 1
        stage_node = trace.stages[0]
        assert isinstance(stage_node, StageTrace)
        assert stage_node.key == "ok"
        assert stage_node.succeeded is True
        assert len(stage_node.steps) == 1
        step_node = stage_node.steps[0]
        assert isinstance(step_node, StepTrace)
        assert step_node.key == "ok"
        assert step_node.succeeded is True
        assert step_node.duration_ms >= 0
        # The flag the step wrote is visible on the context.
        assert ctx.aux["ok"] is True

    @pytest.mark.asyncio
    async def test_trace_to_dict_is_serialisable(self) -> None:
        ctx = PipelineContext()
        await _OkStage().run(ctx)
        data = ExecutionTrace.for_context(ctx).to_dict()
        assert data["stages"][0]["key"] == "ok"
        assert data["stages"][0]["steps"][0]["key"] == "ok"


# ─── AbstractPipeline: topo order + ON_ERROR dispatch ────────────────────────────


class TestPipelineEngine:
    """The engine topo-orders stages and dispatches each stage's declarative ON_ERROR."""

    def test_unknown_after_reference_raises(self) -> None:
        class _Orphan(_OkStage):
            KEY = "orphan"
            AFTER = ("does_not_exist",)

        with pytest.raises(ValueError):
            _OkPipeline([_Orphan()])

    def test_dependency_cycle_raises(self) -> None:
        class _A(_OkStage):
            KEY = "a"
            AFTER = ("b",)

        class _B(_OkStage):
            KEY = "b"
            AFTER = ("a",)

        with pytest.raises(ValueError):
            _OkPipeline([_A(), _B()])

    @pytest.mark.asyncio
    async def test_fail_doc_propagates(self) -> None:
        pipeline = _OkPipeline([_FailFailDocStage()])
        ctx = PipelineContext()
        with pytest.raises(RuntimeError):
            await pipeline.run(ctx)

    @pytest.mark.asyncio
    async def test_skip_policy_continues_run(self) -> None:
        # A failing SKIP stage followed by an OK stage: the run completes and the OK stage runs.
        class _Tail(_OkStage):
            KEY = "tail"
            AFTER = ("boom_skip",)

        pipeline = _OkPipeline([_FailSkipStage(), _Tail()])
        ctx = PipelineContext()
        await pipeline.run(ctx)  # must not raise

        trace = ExecutionTrace.for_context(ctx)
        keys = [s.key for s in trace.stages]
        assert keys == ["boom_skip", "tail"]
        assert trace.stages[0].skipped is True
        assert ctx.aux["ok"] is True
