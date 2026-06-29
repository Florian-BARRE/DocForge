# ====== Code Summary ======
# AbstractStage — the universal stage contract (the second level of Pipeline -> Stage -> Step).
# Fat-abstract / thin-concrete: a concrete stage only DECLARES its identity, ordering, IO, cache
# policy, error policy (the forced ClassVars) and its ordered ``steps``; everything executive —
# the step-iteration template, per-step execution tracking, fingerprint aggregation, describe()
# — is inherited here. The forced ClassVars are enforced at subclass-definition time via
# __init_subclass__ so a stage that forgets one fails loudly at import, not at runtime.
#
# REFACTOR EXCEPTION (>200 lines): this is a single cohesive contract — the ClassVar
# enforcement, the run/track template, fingerprint aggregation, and describe() cannot be split
# without fragmenting one abstraction. The overage is dominated by the mandatory contract docstrings.

# ====== Standard Library Imports ======
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from common_libs.pipeline.base.step.core import AbstractStep, ChainStep
from common_libs.pipeline.bricks.tracking import ExecutionTrace, StageTrace, StepTrace

# ====== Local Project Imports ======
from .keys import StageKey
from .model import CachePolicy, ErrorPolicy, StageSchema, StageSpec

if TYPE_CHECKING:
    from common_libs.pipeline.stages.context import PipelineContext

# Sentinel marking the required SPEC a concrete subclass has not declared.
_UNSET = object()


class AbstractStage(ABC, LoggerClass):
    """
    Universal stage contract — declares ONE ``SPEC`` descriptor, inherits all execution logic.

    A concrete stage declares a single ``SPEC: ClassVar[StageSpec]`` (its identity/ordering/IO/cache
    /error/code-version) and implements the ``steps`` property; everything else — the run/track
    template, fingerprint aggregation, describe(), and the per-field accessors (``key``/``name``/
    ``after``/…) — is inherited and reads from ``SPEC``. ``__init_subclass__`` enforces exactly ONE
    thing: a concrete subclass declares ``SPEC``. An intermediate abstract base (one that specialises
    the contract without being runnable) opts out with ``class X(AbstractStage, abstract=True): ...``.
    """

    # The single forced descriptor (annotation-only on the base; declared by each concrete stage).
    SPEC: ClassVar[StageSpec]

    # Optional Pydantic config model class for the stage (None for config-less stages). Not part of
    # the identity SPEC; surfaced by describe() when present.
    CONFIG: ClassVar[Any] = None

    def __init_subclass__(cls, *, abstract: bool = False, **kwargs: Any) -> None:
        """
        Enforce that every concrete stage subclass declares its ``SPEC``.

        Args:
            abstract (bool): Pass ``abstract=True`` for an intermediate base that specialises
                the contract without being a runnable stage — it skips the SPEC check.

        Raises:
            TypeError: When a concrete subclass omits ``SPEC``.
        """
        super().__init_subclass__(**kwargs)
        if abstract:
            return
        if getattr(cls, "SPEC", _UNSET) is _UNSET:
            raise TypeError(
                f"{cls.__name__} is a concrete AbstractStage but does not declare its "
                f"SPEC: ClassVar[StageSpec]."
            )

    def __init__(self) -> None:
        """Initialise the stage's logger."""
        LoggerClass.__init__(self)

    # ─── SPEC-delegating accessors (one source of truth for stage identity/IO/policy) ───

    @property
    def key(self) -> StageKey:
        """Canonical stage identifier (also the node-cache + fingerprint node id)."""
        return self.SPEC.key

    @property
    def name(self) -> str:
        """Human-readable stage name."""
        return self.SPEC.name

    @property
    def description(self) -> str:
        """One-line description of the stage."""
        return self.SPEC.description

    @property
    def after(self) -> tuple[StageKey, ...]:
        """Stage keys this stage must run after (the DAG edges)."""
        return self.SPEC.after

    @property
    def consumes(self) -> tuple[str, ...]:
        """Context field names the stage reads."""
        return self.SPEC.consumes

    @property
    def produces(self) -> tuple[str, ...]:
        """Context field names the stage writes."""
        return self.SPEC.produces

    @property
    def cache_policy(self) -> CachePolicy:
        """How the pipeline caches the stage."""
        return self.SPEC.cache_policy

    @property
    def error_policy(self) -> ErrorPolicy:
        """What the pipeline does when the stage raises."""
        return self.SPEC.error_policy

    @property
    def code_version(self) -> str:
        """Stage code version fed as ``code_version`` to the node fingerprint."""
        return self.SPEC.code_version

    @property
    @abstractmethod
    def steps(self) -> list[AbstractStep]:
        """The ordered steps this stage executes."""
        ...

    async def run(self, ctx: "PipelineContext") -> None:
        """
        Execute the stage by iterating its steps under unified tracking (the TEMPLATE).

        IO is threaded implicitly through the shared ``PipelineContext``: each step reads what
        it consumes and writes what it produces, so the next step sees the accumulated state.

        Args:
            ctx (PipelineContext): The mutable run accumulator.
        """
        # 1. Open a stage node on the run's execution trace.
        trace = ExecutionTrace.for_context(ctx)
        stage_node = trace.begin_stage(self.key, self.name)

        # 2. Run each step under per-step tracking; mark the stage succeeded only if all do.
        try:
            for step in self.steps:
                await self._run_step_tracked(step, ctx, stage_node)
            stage_node.succeeded = True
        finally:
            trace.end_stage(stage_node)

    async def _run_step_tracked(
        self,
        step: AbstractStep,
        ctx: "PipelineContext",
        stage_node: StageTrace,
    ) -> None:
        """
        Run one step, recording a ``StepTrace`` (timing, success, provider lineage) on the stage.

        Args:
            step (AbstractStep): The step to execute.
            ctx (PipelineContext): The mutable run accumulator.
            stage_node (StageTrace): The open stage node to append the step trace to.

        Raises:
            Exception: Re-raises any step failure after recording it (the pipeline applies the
                stage's ON_ERROR policy).
        """
        # 1. Open the step node and run the step.
        step_node = StepTrace(
            key=step.key,
            name=step.name,
            kind=("chain" if isinstance(step, ChainStep) else "step"),
            started_at=time.perf_counter(),
        )
        try:
            await step.run(ctx)
            step_node.succeeded = True
        except Exception as exc:
            step_node.error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            # 2. Finalise timing + provider lineage, then attach the step node to the stage.
            step_node.duration_ms = int((time.perf_counter() - step_node.started_at) * 1000)
            step_node.chain_attempts = step.trace_attempts()
            step_node.provider = step.trace_final_provider()
            stage_node.steps.append(step_node)

    def fingerprint_params(self) -> dict[str, Any]:
        """
        Aggregate the fingerprint parameters of every step into the stage fingerprint.

        Returns:
            dict[str, Any]: ``{step.key: step.fingerprint_params()}`` for all steps.
        """
        return {step.key: step.fingerprint_params() for step in self.steps}

    def describe(self) -> StageSchema:
        """
        Emit the self-describing schema for this stage, recursing into its steps.

        Returns:
            StageSchema: Identity + ordering + IO + policies + the ordered step schemas.
        """
        config = self.CONFIG
        config_name = config.__name__ if isinstance(config, type) else None
        return StageSchema(
            key=self.key,
            name=self.name,
            description=self.description,
            after=[str(k) for k in self.after],
            consumes=list(self.consumes),
            produces=list(self.produces),
            cache_policy=self.cache_policy,
            on_error=self.error_policy,
            config=config_name,
            steps=[step.describe() for step in self.steps],
        )


__all__ = ["AbstractStage"]
