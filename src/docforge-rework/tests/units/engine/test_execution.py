"""Engine execution semantics: ErrorPolicy SKIP/FAIL, nested groups, progress, timeouts.

Ported from the scratchpad's test_engine_v2.py, split into focused pytest functions with real
assertions (the scratchpad already asserted; this only reorganises + removes the prints).
"""

import asyncio

import pytest

from shared_libs.pipelines.base import (
    ErrorPolicy,
    FromGroupInput,
    FromNode,
    Group,
    OnSuccess,
    ScoreBelow,
    Transition,
)

from .conftest import Cfg, Consumer, Failer, Producer, Scorer, Slow


def test_error_policy_skip_continues_the_pipeline(engine) -> None:
    """A SKIP-policy failure still lets the pipeline continue to the next node."""
    failer = Failer(id="f", config=Cfg())
    failer.ERROR_POLICY = ErrorPolicy.SKIP
    group = Group(
        id="skip",
        children=[failer, Producer(id="p2", config=Cfg(), text="after-skip")],
        transitions=[Transition(from_node_id="f", to_node_id="p2", condition=OnSuccess())],
    )
    output, record = asyncio.run(engine.execute(group, {}))
    assert output.doc.text == "after-skip"
    assert record.status.value == "success"
    statuses = {c.node_id: c.status.value for c in record.children}
    assert statuses == {"f": "skipped", "p2": "success"}


def test_error_policy_fail_stops_the_group(engine) -> None:
    """The default FAIL policy propagates: the group fails, downstream nodes never run."""
    failer = Failer(id="f", config=Cfg())  # default ERROR_POLICY = FAIL
    group = Group(
        id="fail",
        children=[failer, Producer(id="p2", config=Cfg())],
        transitions=[Transition(from_node_id="f", to_node_id="p2", condition=OnSuccess())],
    )
    output, record = asyncio.run(engine.execute(group, {}))
    assert output is None
    assert record.status.value == "failed"
    assert [c.node_id for c in record.children] == ["f"]


@pytest.mark.parametrize(
    ("score", "expected_text"),
    [(0.3, "fallback"), (0.9, "scored")],
    ids=["below_threshold_escalates", "above_threshold_stays"],
)
def test_score_below_escalation(engine, score: float, expected_text: str) -> None:
    """ScoreBelow escalates to the fallback only when the producer's score is under threshold."""
    group = Group(
        id="score",
        children=[Scorer(id="sc", config=Cfg(), score=score), Producer(id="fb", config=Cfg(), text="fallback")],
        transitions=[Transition(from_node_id="sc", to_node_id="fb", condition=ScoreBelow(threshold=0.5))],
    )
    output, _ = asyncio.run(engine.execute(group, {}))
    assert output.doc.text == expected_text


def test_nested_group_from_group_input(engine) -> None:
    """A nested group's child reads a FromGroupInput field bound by the outer group."""
    inner = Group(
        id="wrapper",
        children=[Consumer(id="ic", config=Cfg())],
        bindings={"ic": {"doc": FromGroupInput(field_name="doc")}},
    )
    outer = Group(
        id="outer",
        children=[Producer(id="seed", config=Cfg(), text="seed"), inner],
        transitions=[Transition(from_node_id="seed", to_node_id="wrapper", condition=OnSuccess())],
        bindings={"seed": {}, "wrapper": {"doc": FromNode(node_id="seed", field_name="doc")}},
    )
    output, _ = asyncio.run(engine.execute(outer, {}))
    assert output.doc.text == "seed -> C"


def test_progress_callback_fires_start_and_end_per_child(engine) -> None:
    """The progress callback fires for every child, in wiring order."""
    events = []

    async def callback(event) -> None:
        events.append((str(event.phase), event.node_id, str(event.record.status) if event.record else "-"))

    group = Group(
        id="prog",
        children=[Producer(id="a", config=Cfg()), Producer(id="b", config=Cfg())],
        transitions=[Transition(from_node_id="a", to_node_id="b", condition=OnSuccess())],
    )
    asyncio.run(engine.execute(group, {}, progress_callback=callback))
    node_ids = [node_id for _, node_id, _ in events]
    assert "a" in node_ids and "b" in node_ids


def test_run_timeout_fails_the_group_loudly(engine) -> None:
    """A node exceeding the run's deadline fails the group with a timeout error, not a hang."""
    group = Group(id="to", children=[Slow(id="s", config=Cfg())])
    output, record = asyncio.run(engine.execute(group, {}, timeout_seconds=0.1))
    assert output is None
    assert record.status.value == "failed"
    assert record.error is not None
