"""WhenEquals switch routing + priority vs ScoreBelow (ported from test_when_equals.py)."""

import asyncio

import pytest

from shared_libs.pipelines.base import (
    ActionNode,
    Group,
    NodeConfig,
    NodeInput,
    NodeOutput,
    ScoreBelow,
    ScoredOutput,
    Transition,
    WhenEquals,
)
from shared_libs.public_models import Artifact


class Tag(Artifact):
    value: str = ""


class Empty(NodeInput):
    pass


class KindOut(ScoredOutput):
    tag: Tag
    kind: str = ""


class TagOut(NodeOutput):
    tag: Tag


class Classifier(ActionNode):
    KIND = "test_cond_classifier"
    NAME = "C"
    SUMMARY = "s"
    Config = NodeConfig
    Consumes = Empty
    Produces = KindOut

    def __init__(self, id: str, config: NodeConfig, kind: str, score: float = 1.0) -> None:
        super().__init__(id, config)
        self._kind, self._score = kind, score

    async def run(self, data: Empty) -> KindOut:
        return KindOut(tag=Tag(), kind=self._kind, score=self._score)


class Path(ActionNode):
    KIND = "test_cond_path"
    NAME = "P"
    SUMMARY = "s"
    Config = NodeConfig
    Consumes = Empty
    Produces = TagOut

    def __init__(self, id: str, config: NodeConfig, label: str) -> None:
        super().__init__(id, config)
        self._label = label

    async def run(self, data: Empty) -> TagOut:
        return TagOut(tag=Tag(value=self._label))


def _build(kind: str, score: float = 1.0, with_escalation: bool = False) -> Group:
    children = [
        Classifier("clf", NodeConfig(), kind, score),
        Path("photo_path", NodeConfig(), "PHOTO-PATH"),
        Path("scan_path", NodeConfig(), "SCAN-PATH"),
    ]
    if with_escalation:
        children.append(Path("rescue", NodeConfig(), "RESCUE"))
    transitions = [
        Transition(from_node_id="clf", to_node_id="photo_path", condition=WhenEquals(field="kind", equals="photo")),
        Transition(
            from_node_id="clf", to_node_id="scan_path", condition=WhenEquals(field="kind", equals="scanned_text")
        ),
    ]
    if with_escalation:
        transitions.append(Transition(from_node_id="clf", to_node_id="rescue", condition=ScoreBelow(threshold=0.5)))
    return Group(id="g", children=children, transitions=transitions, bindings={})


@pytest.mark.parametrize(
    ("kind", "expected_label"), [("photo", "PHOTO-PATH"), ("scanned_text", "SCAN-PATH")]
)
def test_switch_routes_each_kind_to_its_branch(engine, kind: str, expected_label: str) -> None:
    output, _ = asyncio.run(engine.execute(_build(kind), {}))
    assert output.tag.value == expected_label


def test_unmatched_value_stops_at_the_terminal(engine) -> None:
    """An unmatched switch value has no outgoing edge: the classifier's own output is final."""
    output, record = asyncio.run(engine.execute(_build("decorative"), {}))
    assert output.kind == "decorative"
    assert len(record.children) == 1


def test_score_below_priority_beats_when_equals(engine) -> None:
    """A bad score escalates BEFORE routing by value, even though both edges could fire."""
    output, _ = asyncio.run(engine.execute(_build("photo", score=0.2, with_escalation=True), {}))
    assert output.tag.value == "RESCUE"


def test_valid_switch_with_escalation_has_zero_issues(validator) -> None:
    assert validator.validate(_build("photo", with_escalation=True)) == []


def test_duplicate_when_equals_value_is_ambiguous(validator) -> None:
    graph = _build("photo")
    graph.transitions.append(
        Transition(from_node_id="clf", to_node_id="photo_path", condition=WhenEquals(field="kind", equals="photo"))
    )
    codes = {issue.code.value for issue in validator.validate(graph)}
    assert "ambiguous_routing" in codes


def test_when_equals_on_two_fields_is_ambiguous_and_flags_unknown_field(validator) -> None:
    graph = _build("photo")
    graph.transitions.append(
        Transition(from_node_id="clf", to_node_id="scan_path", condition=WhenEquals(field="other", equals="x"))
    )
    codes = {issue.code.value for issue in validator.validate(graph)}
    assert "ambiguous_routing" in codes
    assert "when_equals_unknown_field" in codes


def test_when_equals_condition_round_trips_through_json() -> None:
    transition = Transition(from_node_id="a", to_node_id="b", condition=WhenEquals(field="kind", equals="chart"))
    again = Transition.model_validate(transition.model_dump(mode="json"))
    assert isinstance(again.condition, WhenEquals)
    assert again.condition.equals == "chart"
