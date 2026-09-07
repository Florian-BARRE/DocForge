"""The engine lifts a scored node's quality score onto its execution record — like ``_usage``,
independently of the trace level — and leaves it None for a non-scored node."""

import asyncio

import pytest

from shared_libs.pipelines.base import Group
from shared_libs.pipelines.engine import FlowEngine, TraceLevel

from .conftest import Cfg, Producer, Scorer


def test_scored_node_record_carries_its_score(engine) -> None:
    """A scored node's record reports its ScoredOutput.score."""
    group = Group(id="g", children=[Scorer(id="sc", config=Cfg(), score=0.73)])
    _, record = asyncio.run(engine.execute(group, {}))
    assert record.children[0].score == pytest.approx(0.73)


def test_non_scored_node_record_score_is_none(engine) -> None:
    """A plain-output node leaves its record score None."""
    group = Group(id="g", children=[Producer(id="p", config=Cfg())])
    _, record = asyncio.run(engine.execute(group, {}))
    assert record.children[0].score is None


def test_score_survives_trace_off() -> None:
    """The score is lifted off the output even when nothing is captured (the search runner's mode)."""
    engine = FlowEngine(trace_level=TraceLevel.OFF)
    group = Group(id="g", children=[Scorer(id="sc", config=Cfg(), score=0.42)])
    _, record = asyncio.run(engine.execute(group, {}))
    leaf = record.children[0]
    # Nothing captured (a trace, not a store) yet the score still rides on the record.
    assert leaf.output is None
    assert leaf.output_summary is None
    assert leaf.score == pytest.approx(0.42)
