# ====== Code Summary ======
# Runs one engine scenario and returns everything observable about it: the final output, the record
# tree and the ordered progress events. The progress log is collected by a callback that never raises
# (the abort scenarios build their own callback); a scenario may also attach a cache hook or a resume
# point. Wall-clock timing is the only thing left out.

# ====== Standard Library Imports ======
import asyncio
from dataclasses import dataclass, field
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import Group, NodeExecutionRecord, NodeOutput
from shared_libs.pipelines.engine import (
    CacheHook,
    FlowEngine,
    ProgressEvent,
    ResumePoint,
    TraceLevel,
)


@dataclass
class EngineRun:
    """What one scenario produced.

    Attributes:
        output (NodeOutput | None): The run's final output (None when the run failed).
        record (NodeExecutionRecord): The recursive execution record.
        events (list[ProgressEvent]): The progress events, in firing order.
    """

    output: NodeOutput | None
    record: NodeExecutionRecord
    events: list[ProgressEvent] = field(default_factory=list)


class EngineRunner:
    """Runs a group through a fresh FlowEngine and collects the progress events."""

    @staticmethod
    def run(
        group: Group,
        run_input: dict[str, Any] | None = None,
        trace_level: TraceLevel = TraceLevel.FULL,
        cache_hook: CacheHook | None = None,
        resume: ResumePoint | None = None,
        timeout_seconds: float | None = None,
    ) -> EngineRun:
        """Execute ``group`` to completion and return the output, the record tree and the events."""
        events: list[ProgressEvent] = []

        async def collect(event: ProgressEvent) -> None:
            events.append(event)

        output, record = asyncio.run(
            FlowEngine(trace_level).execute(
                group,
                run_input or {},
                timeout_seconds=timeout_seconds,
                progress_callback=collect,
                cache_hook=cache_hook,
                resume=resume,
            )
        )
        return EngineRun(output=output, record=record, events=events)
