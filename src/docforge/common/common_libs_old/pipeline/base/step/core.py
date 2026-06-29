# ====== Code Summary ======
# AbstractStep — the universal step contract (the third level of Pipeline -> Stage -> Step).
# A step is the smallest executable unit: it reads what it consumes from the PipelineContext,
# does one thing, and writes what it produces back. The base supplies identity ClassVars,
# describe(), and the tracing hooks; concrete steps implement run().
#
# ChainStep — the chain-backed step subtype. It holds a Chain[T, R] brick (provider escalation
# + gate + budget + call-cache), executes it via Chain.call, and exposes the per-attempt
# lineage to the tracking layer. describe() emits the provider category + the ordered provider
# choices so the self-describing API can render the escalation ladder.
#
# REFACTOR EXCEPTION (>200 lines): AbstractStep and its ChainStep subtype are one cohesive
# contract (identity/IO + the chain-backed specialisation); the overage is dominated by the
# mandatory Google-style contract docstrings + the per-instance property overrides.

# ====== Standard Library Imports ======
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, ClassVar

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from common_libs.pipeline.bricks.chain import Chain, ChainAttempt, ChainHelpers, ChainOutcome

# ====== Local Project Imports ======
from .model import StepSchema

if TYPE_CHECKING:
    from common_libs.pipeline.stages.context import PipelineContext


class AbstractStep(ABC, LoggerClass):
    """
    Universal step contract — the smallest executable unit of the pipeline.

    Identity is carried as ClassVars (``KEY``/``NAME``/``DESCRIPTION``) plus typed IO
    (``CONSUMES``/``PRODUCES``); subtypes whose identity is instance-specific (e.g.
    ``ChainStep``) override the corresponding read-only properties instead. The base provides
    ``describe()`` and the two tracing hooks (``trace_attempts`` / ``trace_final_provider``);
    concrete steps implement ``run(ctx)``.
    """

    # ─── Identity + IO ClassVars (instance subtypes may override the properties below) ───
    KEY: ClassVar[str] = ""
    NAME: ClassVar[str] = ""
    DESCRIPTION: ClassVar[str] = ""
    CONSUMES: ClassVar[tuple[str, ...]] = ()
    PRODUCES: ClassVar[tuple[str, ...]] = ()

    def __init__(self) -> None:
        """Initialise the step's logger."""
        LoggerClass.__init__(self)

    @abstractmethod
    async def run(self, ctx: "PipelineContext") -> None:
        """
        Execute the step, reading ``CONSUMES`` and writing ``PRODUCES`` on the context.

        Args:
            ctx (PipelineContext): The mutable run accumulator.
        """
        ...

    @property
    def key(self) -> str:
        """Stable step identifier."""
        return self.KEY

    @property
    def name(self) -> str:
        """Human-readable step name."""
        return self.NAME

    @property
    def description(self) -> str:
        """One-line description of the step."""
        return self.DESCRIPTION

    @property
    def consumes(self) -> tuple[str, ...]:
        """Context keys this step reads."""
        return self.CONSUMES

    @property
    def produces(self) -> tuple[str, ...]:
        """Context keys this step writes."""
        return self.PRODUCES

    def fingerprint_params(self) -> dict[str, Any]:
        """
        Return the parameters that, when changed, must invalidate this step's cache.

        Returns:
            dict[str, Any]: Fingerprint contribution (empty for a side-effect-free step).
        """
        return {}

    def trace_attempts(self) -> list[ChainAttempt]:
        """Return the per-provider attempts of the last run (empty for non-chain steps)."""
        return []

    def trace_final_provider(self) -> str | None:
        """Return the final provider id of the last run (None for non-chain steps)."""
        return None

    def describe(self) -> StepSchema:
        """
        Emit the self-describing schema for this step.

        Returns:
            StepSchema: Identity + typed IO for a plain step.
        """
        return StepSchema(
            kind="step",
            key=self.key,
            name=self.name,
            description=self.description,
            consumes=list(self.consumes),
            produces=list(self.produces),
        )


class ChainStep(AbstractStep):
    """
    Chain-backed step: executes a ``Chain[T, R]`` (provider escalation + gate + call-cache).

    The chain's per-provider call is built per run by ``call_builder(ctx)`` and the accepted
    result is written onto the context by ``writer(ctx, outcome)`` — both injected so the same
    ChainStep machinery serves any provider category. ``describe()`` emits the provider
    ``category`` and the ordered provider choices; the per-attempt lineage flows to the trace.
    """

    def __init__(
        self,
        *,
        key: str,
        name: str,
        description: str,
        category: str,
        chain: Chain[Any, Any],
        call_builder: Callable[["PipelineContext"], Callable[[Any], Awaitable[Any]]],
        writer: Callable[["PipelineContext", ChainOutcome[Any]], None],
        consumes: tuple[str, ...] = (),
        produces: tuple[str, ...] = (),
    ) -> None:
        """
        Wire a chain-backed step.

        Args:
            key (str): Stable step identifier.
            name (str): Human-readable step name.
            description (str): One-line description.
            category (str): Provider category this chain serves (e.g. ``"embed"``).
            chain (Chain[Any, Any]): The provider escalation chain to execute.
            call_builder (Callable): ``(ctx) -> (provider -> awaitable)`` — builds the per-run
                provider call from the context (e.g. the texts to embed).
            writer (Callable): ``(ctx, outcome) -> None`` — writes the chain outcome onto ctx.
            consumes (tuple[str, ...]): Context keys read.
            produces (tuple[str, ...]): Context keys written.
        """
        AbstractStep.__init__(self)
        self._key = key
        self._name = name
        self._description = description
        self._category = category
        self._chain = chain
        self._call_builder = call_builder
        self._writer = writer
        self._consumes = tuple(consumes)
        self._produces = tuple(produces)
        self._last_outcome: ChainOutcome[Any] | None = None

    @property
    def key(self) -> str:
        """Stable step identifier."""
        return self._key

    @property
    def name(self) -> str:
        """Human-readable step name."""
        return self._name

    @property
    def description(self) -> str:
        """One-line description of the step."""
        return self._description

    @property
    def consumes(self) -> tuple[str, ...]:
        """Context keys this step reads."""
        return self._consumes

    @property
    def produces(self) -> tuple[str, ...]:
        """Context keys this step writes."""
        return self._produces

    @property
    def category(self) -> str:
        """Provider category served by this chain step."""
        return self._category

    @property
    def chain(self) -> Chain[Any, Any]:
        """The underlying provider escalation chain."""
        return self._chain

    async def run(self, ctx: "PipelineContext") -> None:
        """
        Execute the chain for this run and write its outcome onto the context.

        Args:
            ctx (PipelineContext): The mutable run accumulator.
        """
        # 1. Run the chain with the per-run provider call built from the context.
        outcome = await self._chain.call(self._call_builder(ctx))

        # 2. Remember the outcome for the tracing hooks, then write it onto the context.
        self._last_outcome = outcome
        self._writer(ctx, outcome)

    def fingerprint_params(self) -> dict[str, Any]:
        """Return the chain signature — any provider/version change invalidates the cache."""
        return {"chain": self._chain.signature()}

    def trace_attempts(self) -> list[ChainAttempt]:
        """Return the per-provider attempts captured by the last chain run."""
        return list(self._last_outcome.attempts) if self._last_outcome is not None else []

    def trace_final_provider(self) -> str | None:
        """Return the provider id whose result the chain accepted on the last run."""
        return self._last_outcome.final_provider if self._last_outcome is not None else None

    def describe(self) -> StepSchema:
        """
        Emit the self-describing schema for this chain step.

        Returns:
            StepSchema: Identity + typed IO + provider category + ordered provider choices.
        """
        return StepSchema(
            kind="chain",
            key=self.key,
            name=self.name,
            description=self.description,
            consumes=list(self.consumes),
            produces=list(self.produces),
            category=self._category,
            providers=[ChainHelpers.default_provider_id(p) for p in self._chain.providers],
        )


__all__ = ["AbstractStep", "ChainStep"]
