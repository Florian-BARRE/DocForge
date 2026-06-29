# ====== Code Summary ======
# ExecutionTrace — the single, unified tracking collector for the dynamic pipeline.
# It accumulates the hierarchical pipeline -> stage -> step -> chain-attempt tree that the
# abstract run() helpers populate (`_run_stage_tracked` / `_run_step_tracked`). One mechanism
# for everything; `to_dict()` serialises the whole tree for the existing inspect UI.
# A trace is bound to a pipeline context (stored under ``ctx.aux["execution_trace"]``) so any
# stage run — standalone (unit test) or under a full pipeline — accumulates into the same tree.

# ====== Standard Library Imports ======
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

# ====== Local Project Imports ======
from .models import StageTrace

if TYPE_CHECKING:
    from common_libs.pipelines.base.context import PipelineContextBase

# Key under which the active ExecutionTrace lives on the pipeline context's ``aux`` store.
_CTX_AUX_KEY = "execution_trace"


@dataclass
class ExecutionTrace:
    """
    Mutable collector for one pipeline run's hierarchical execution trace.

    The abstract classes drive it: the pipeline brackets a run with
    ``begin_pipeline``/``end_pipeline`` and brackets each stage with
    ``begin_stage``/``end_stage``; the stage appends ``StepTrace`` nodes into the
    currently-open ``StageTrace`` as it runs each step.

    Attributes:
        pipeline_key (str): Stable identifier of the pipeline being traced.
        pipeline_name (str): Human-readable pipeline name.
        started_at (float): ``time.perf_counter()`` at pipeline start.
        duration_ms (int): Wall-clock duration of the whole pipeline run.
        stages (list[StageTrace]): One entry per stage, in execution order.
    """

    pipeline_key: str = ""
    pipeline_name: str = ""
    started_at: float = 0.0
    duration_ms: int = 0
    stages: list[StageTrace] = field(default_factory=list)

    @classmethod
    def for_context(cls, ctx: "PipelineContextBase") -> "ExecutionTrace":
        """
        Return the trace bound to ``ctx``, creating and attaching one on first access.

        Args:
            ctx (PipelineContextBase): The active pipeline context.

        Returns:
            ExecutionTrace: The trace stored under ``ctx.aux["execution_trace"]``.
        """
        # 1. Reuse the existing trace when one is already attached to the context.
        trace = ctx.aux.get(_CTX_AUX_KEY)
        if isinstance(trace, cls):
            return trace

        # 2. Otherwise create a fresh trace and attach it for the rest of the run.
        trace = cls()
        ctx.aux[_CTX_AUX_KEY] = trace
        return trace

    def begin_pipeline(self, key: str, name: str) -> None:
        """
        Record the pipeline identity and start the pipeline clock.

        Args:
            key (str): Stable pipeline identifier.
            name (str): Human-readable pipeline name.
        """
        self.pipeline_key = key
        self.pipeline_name = name
        self.started_at = time.perf_counter()

    def end_pipeline(self) -> None:
        """Stop the pipeline clock and record the total duration."""
        self.duration_ms = int((time.perf_counter() - self.started_at) * 1000)

    def begin_stage(self, key: str, name: str) -> StageTrace:
        """
        Open a new stage node, append it, and return it as the current stage.

        Args:
            key (str): Stable stage identifier.
            name (str): Human-readable stage name.

        Returns:
            StageTrace: The freshly opened, not-yet-finalised stage node.
        """
        node = StageTrace(key=key, name=name, started_at=time.perf_counter())
        self.stages.append(node)
        return node

    @staticmethod
    def end_stage(node: StageTrace) -> None:
        """
        Finalise a stage node by recording its duration.

        Args:
            node (StageTrace): The stage node returned by ``begin_stage``.
        """
        node.duration_ms = int((time.perf_counter() - node.started_at) * 1000)

    def mark_last_stage_error(self, error: str) -> None:
        """
        Stamp an error on the most recently opened stage (used by ON_ERROR handling).

        Args:
            error (str): The exception summary to record.
        """
        if self.stages:
            self.stages[-1].error = error
            self.stages[-1].succeeded = False

    def mark_last_stage_degraded(self) -> None:
        """Flag the most recently opened stage as degraded (ON_ERROR=DEGRADE)."""
        if self.stages:
            self.stages[-1].degraded = True

    def mark_last_stage_skipped(self) -> None:
        """Flag the most recently opened stage as skipped (ON_ERROR=SKIP)."""
        if self.stages:
            self.stages[-1].skipped = True

    def to_dict(self) -> dict[str, Any]:
        """Return a plain-dict view of the whole trace tree (feeds the inspect UI)."""
        return {
            "pipeline": self.pipeline_key,
            "name": self.pipeline_name,
            "duration_ms": self.duration_ms,
            "stages": [s.to_dict() for s in self.stages],
        }


__all__ = ["ExecutionTrace"]
