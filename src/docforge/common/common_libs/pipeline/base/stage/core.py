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
from .model import CachePolicy, ErrorPolicy, StageSchema

if TYPE_CHECKING:
    from common_libs.pipeline.stages.context import PipelineContext

# Sentinel marking a required ClassVar that a concrete subclass has not declared.
_UNSET = object()


class AbstractStage(ABC, LoggerClass):
    """
    Universal stage contract — declares identity/IO/policy, inherits all execution logic.

    Forced ClassVars (enforced on every concrete subclass via ``__init_subclass__``):
        KEY (str): Stable stage identifier, unique within the pipeline.
        NAME (str): Human-readable stage name.
        DESCRIPTION (str): One-line description.
        AFTER (tuple[str, ...]): Keys of stages this stage must run after (the DAG edges).
        CONFIG (Any): The stage's Pydantic config model class, or ``None``.
        CONSUMES (tuple[str, ...]): Context keys read.
        PRODUCES (tuple[str, ...]): Context keys written.
        CACHE_POLICY (CachePolicy): How the pipeline caches the stage.
        ON_ERROR (ErrorPolicy): What the pipeline does when the stage raises.

    Optional ClassVar (has a default, not forced):
        NODE_VERSION (str): Stage code version — bumped to invalidate the node cache. Fed as
            ``code_version`` to ``compute_fingerprint`` by the caching middleware (PR-3), exactly
            as the legacy ``_S{0,1,2}_NODE_VERSION`` constants do today.

    A concrete stage additionally implements the ``steps`` property. An intermediate abstract
    base (one that specialises the contract without being runnable) opts out of the ClassVar
    check with ``class IngestStage(AbstractStage, abstract=True): ...``.
    """

    # ─── Forced identity / ordering / IO / policy ClassVars (annotation-only on the base) ───
    KEY: ClassVar[str]
    NAME: ClassVar[str]
    DESCRIPTION: ClassVar[str]
    AFTER: ClassVar[tuple[str, ...]]
    CONFIG: ClassVar[Any]
    CONSUMES: ClassVar[tuple[str, ...]]
    PRODUCES: ClassVar[tuple[str, ...]]
    CACHE_POLICY: ClassVar[CachePolicy]
    ON_ERROR: ClassVar[ErrorPolicy]

    # Optional: the stage's code version, fed as ``code_version`` to the node fingerprint (PR-3).
    NODE_VERSION: ClassVar[str] = "1.0"

    # Optional: the cache identity of this node (fingerprint ``node_type`` + node-cache ``node_id``).
    # Empty ("") means "use the KEY"; the NODE_CACHED adapters override it to the legacy ids
    # ("s0"/"s1"/"s2") so cache keys + stage_run rows stay byte-identical to the legacy engine.
    NODE_TYPE: ClassVar[str] = ""

    _REQUIRED_CLASSVARS: ClassVar[tuple[str, ...]] = (
        "KEY",
        "NAME",
        "DESCRIPTION",
        "AFTER",
        "CONFIG",
        "CONSUMES",
        "PRODUCES",
        "CACHE_POLICY",
        "ON_ERROR",
    )

    def __init_subclass__(cls, *, abstract: bool = False, **kwargs: Any) -> None:
        """
        Enforce the forced ClassVar contract on every concrete stage subclass.

        Args:
            abstract (bool): Pass ``abstract=True`` for an intermediate base that specialises
                the contract without being a runnable stage — it skips the ClassVar check.

        Raises:
            TypeError: When a concrete subclass omits one or more required ClassVars.
        """
        super().__init_subclass__(**kwargs)
        if abstract:
            return
        missing = [
            name
            for name in cls._REQUIRED_CLASSVARS
            if getattr(cls, name, _UNSET) is _UNSET
        ]
        if missing:
            raise TypeError(
                f"{cls.__name__} is a concrete AbstractStage but does not declare the "
                f"required ClassVar(s): {', '.join(missing)}."
            )

    def __init__(self) -> None:
        """Initialise the stage's logger."""
        LoggerClass.__init__(self)

    @property
    def node_type(self) -> str:
        """
        The cache identity: the node fingerprint ``node_type`` AND the node-cache ``node_id``.

        Defaults to the stage ``KEY``; a stage overrides ``NODE_TYPE`` to pin a legacy id
        (e.g. ``"s0"``) so its Merkle fingerprint + stage_run rows match the legacy engine exactly.

        Returns:
            str: ``self.NODE_TYPE`` when set, else ``self.KEY``.
        """
        return self.NODE_TYPE or self.KEY

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
        stage_node = trace.begin_stage(self.KEY, self.NAME)

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
            key=self.KEY,
            name=self.NAME,
            description=self.DESCRIPTION,
            after=list(self.AFTER),
            consumes=list(self.CONSUMES),
            produces=list(self.PRODUCES),
            cache_policy=self.CACHE_POLICY,
            on_error=self.ON_ERROR,
            config=config_name,
            steps=[step.describe() for step in self.steps],
        )


__all__ = ["AbstractStage"]
