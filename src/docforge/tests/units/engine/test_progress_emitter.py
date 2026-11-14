"""ProgressEmitter: fires the caller-owned callback and marks an aborting callback on the context."""

import asyncio

import pytest

from shared_libs.pipelines.base import Group
from shared_libs.pipelines.engine import ProgressEvent, ProgressPhase, RunContext
from shared_libs.pipelines.engine.progress_emitter import ProgressEmitter


def test_no_callback_is_a_no_op() -> None:
    context = RunContext(run_input={})
    asyncio.run(ProgressEmitter.emit(context, ProgressPhase.START, Group(id="g", children=[])))
    assert context.callback_error is None


def test_event_carries_node_phase_and_total_items() -> None:
    events: list[ProgressEvent] = []

    async def callback(event: ProgressEvent) -> None:
        events.append(event)

    context = RunContext(run_input={}, progress_callback=callback)
    group = Group(id="g", children=[])
    asyncio.run(ProgressEmitter.emit(context, ProgressPhase.START, group, total_items=3))
    assert [(e.phase, e.node_id, e.kind, e.total_items) for e in events] == [
        (ProgressPhase.START, "g", group.KIND, 3)
    ]


def test_raising_callback_is_marked_and_propagates_unchanged() -> None:
    abort = RuntimeError("cancel")

    async def callback(event: ProgressEvent) -> None:
        raise abort

    context = RunContext(run_input={}, progress_callback=callback)
    with pytest.raises(RuntimeError) as raised:
        asyncio.run(ProgressEmitter.emit(context, ProgressPhase.END, Group(id="g", children=[])))
    assert raised.value is abort
    assert context.callback_error is abort
