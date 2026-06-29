# ====== Code Summary ======
# Test-only step scaffolding for the dynamic-pipeline contract/engine unit tests. RunnerStep is a
# concrete AbstractStep whose body is an injected coroutine — the test analogue of the production
# DelegatingStep (removed once every ingest stage became native). Not a test module itself (no
# ``test_`` prefix), so pytest does not collect it.

# ====== Standard Library Imports ======
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

# ====== Internal Project Imports ======
from common_libs.pipeline.base.step.core import AbstractStep

if TYPE_CHECKING:
    from common_libs.pipeline.stages.context import PipelineContext


class RunnerStep(AbstractStep):
    """
    A single step whose execution is delegated to an injected coroutine (test scaffolding).

    Identity and IO are provided per instance, mirroring how the old production DelegatingStep was
    wired so the contract/engine tests can build trivial stages without a real provider chain.
    """

    def __init__(
        self,
        *,
        key: str,
        name: str,
        description: str,
        consumes: tuple[str, ...],
        produces: tuple[str, ...],
        runner: Callable[["PipelineContext"], Awaitable[None]],
    ) -> None:
        """
        Wire a runner step.

        Args:
            key (str): Stable step identifier.
            name (str): Human-readable step name.
            description (str): One-line description.
            consumes (tuple[str, ...]): Context keys read by the delegated run.
            produces (tuple[str, ...]): Context keys written by the delegated run.
            runner (Callable): The coroutine that performs the work, given the context.
        """
        AbstractStep.__init__(self)
        self._key = key
        self._name = name
        self._description = description
        self._consumes = tuple(consumes)
        self._produces = tuple(produces)
        self._runner = runner

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

    async def run(self, ctx: "PipelineContext") -> None:
        """Execute the injected runner."""
        await self._runner(ctx)


__all__ = ["RunnerStep"]
