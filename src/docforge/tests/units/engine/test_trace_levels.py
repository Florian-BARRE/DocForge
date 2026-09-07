"""FlowEngine capture by trace level: OFF captures nothing, SHAPE captures only the cheap summary,
FULL captures the summary AND the full stripped dump. Same single-node group the score-capture
tests use (Producer — a plain, non-scored leaf)."""

import asyncio

from shared_libs.pipelines.base import Group
from shared_libs.pipelines.engine import FlowEngine, TraceLevel

from .conftest import Cfg, Producer


def _run(trace_level: TraceLevel):
    engine = FlowEngine(trace_level=trace_level)
    group = Group(id="g", children=[Producer(id="p", config=Cfg(), text="hello")])
    _, record = asyncio.run(engine.execute(group, {}))
    return record.children[0]


def test_trace_off_captures_neither_summary_nor_full() -> None:
    leaf = _run(TraceLevel.OFF)
    assert leaf.input_summary is None
    assert leaf.output_summary is None
    assert leaf.resolved_input is None
    assert leaf.output is None


def test_trace_shape_captures_only_the_summary() -> None:
    leaf = _run(TraceLevel.SHAPE)
    assert leaf.input_summary is not None
    assert leaf.output_summary is not None
    assert leaf.output_summary["type"] == "DocOut"
    # The heavy full-stripped dump is NOT paid for at the shape tier.
    assert leaf.resolved_input is None
    assert leaf.output is None


def test_trace_full_captures_both_summary_and_full_dump() -> None:
    leaf = _run(TraceLevel.FULL)
    assert leaf.input_summary is not None
    assert leaf.output_summary is not None
    assert leaf.resolved_input is not None
    assert leaf.output is not None
    # The full dump carries the actual content (unlike the size-only summary).
    assert leaf.output["doc"]["text"] == "hello"
