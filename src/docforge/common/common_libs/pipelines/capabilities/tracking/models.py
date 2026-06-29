# ====== Code Summary ======
# Hierarchical execution-trace data model for the dynamic pipeline architecture.
# A run accumulates one tree: pipeline -> stage -> step -> chain-attempt. The chain-attempt
# level REUSES the chain brick's ChainAttempt type (no reinvention) so the per-provider
# escalation lineage already produced by Chain.call flows straight into the trace.
# Pure data: no I/O, no logging — mutable dataclasses filled by the abstract run() helpers.

# ====== Standard Library Imports ======
from dataclasses import dataclass, field
from typing import Any

# ====== Internal Project Imports ======
from common_libs.pipelines.capabilities.chain import ChainAttempt


@dataclass
class StepTrace:
    """
    One step within a stage — what the step did and (for chain steps) which providers ran.

    Attributes:
        key (str): Stable step identifier.
        name (str): Human-readable step name.
        kind (str): ``"step"`` for a plain step, ``"chain"`` for a ``ChainStep``.
        started_at (float): ``time.perf_counter()`` taken when the step began.
        duration_ms (int): Wall-clock duration of the step.
        succeeded (bool): True when the step's ``run`` returned without raising.
        error (str | None): Exception summary when the step raised.
        provider (str | None): Final provider id (chain steps only).
        chain_attempts (list[ChainAttempt]): Per-provider attempts (chain steps only).
    """

    key: str
    name: str
    kind: str = "step"
    started_at: float = 0.0
    duration_ms: int = 0
    succeeded: bool = False
    error: str | None = None
    provider: str | None = None
    chain_attempts: list[ChainAttempt] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a plain-dict view of this step trace (feeds the inspect UI)."""
        return {
            "key": self.key,
            "name": self.name,
            "kind": self.kind,
            "duration_ms": self.duration_ms,
            "succeeded": self.succeeded,
            "error": self.error,
            "provider": self.provider,
            "attempts": [
                {
                    "provider_id": a.provider_id,
                    "score": a.score,
                    "duration_ms": a.duration_ms,
                    "succeeded": a.succeeded,
                    "escalated": a.escalated,
                    "error": a.error,
                }
                for a in self.chain_attempts
            ],
        }


@dataclass
class StageTrace:
    """
    One stage within the pipeline — its steps plus stage-level execution metadata.

    Attributes:
        key (str): Stable stage identifier.
        name (str): Human-readable stage name.
        started_at (float): ``time.perf_counter()`` taken when the stage began.
        duration_ms (int): Wall-clock duration of the stage.
        succeeded (bool): True when every step completed without raising.
        error (str | None): Exception summary when the stage raised.
        cache_hit (bool): True when the stage was served from the node cache.
        degraded (bool): True when the stage ran under an ``ON_ERROR=DEGRADE`` recovery.
        skipped (bool): True when the stage was skipped via ``ON_ERROR=SKIP``.
        steps (list[StepTrace]): One entry per step executed, in order.
    """

    key: str
    name: str
    started_at: float = 0.0
    duration_ms: int = 0
    succeeded: bool = False
    error: str | None = None
    cache_hit: bool = False
    degraded: bool = False
    skipped: bool = False
    steps: list[StepTrace] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a plain-dict view of this stage trace (feeds the inspect UI)."""
        return {
            "key": self.key,
            "name": self.name,
            "duration_ms": self.duration_ms,
            "succeeded": self.succeeded,
            "error": self.error,
            "cache_hit": self.cache_hit,
            "degraded": self.degraded,
            "skipped": self.skipped,
            "steps": [s.to_dict() for s in self.steps],
        }


__all__ = ["StepTrace", "StageTrace"]
