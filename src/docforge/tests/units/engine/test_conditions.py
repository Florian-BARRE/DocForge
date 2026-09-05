"""WhenEquals switch routing + priority vs ScoreBelow (ported from test_when_equals.py)."""

import asyncio

import pytest

from shared_libs.pipelines.base import (
    ActionNode,
    Always,
    Group,
    NodeConfig,
    NodeInput,
    NodeOutput,
    OnFailure,
    OnSuccess,
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


class Failer(ActionNode):
    KIND = "test_cond_failer"
    NAME = "F"
    SUMMARY = "s"
    Config = NodeConfig
    Consumes = Empty
    Produces = TagOut

    async def run(self, data: Empty) -> TagOut:
        raise RuntimeError("boom")


def _build(kind: str, score: float = 1.0, with_escalation: bool = False) -> Group:
    children = [
        Classifier("clf", NodeConfig(), kind, score),
        Path("photo_path", NodeConfig(), "PHOTO-PATH"),
        Path("scan_path", NodeConfig(), "SCAN-PATH"),
    ]
    if with_escalation:
        children.append(Path("rescue", NodeConfig(), "RESCUE"))
    transitions = [
        Transition(
            from_node_id="clf",
            to_node_id="photo_path",
            condition=WhenEquals(field="kind", equals="photo"),
        ),
        Transition(
            from_node_id="clf",
            to_node_id="scan_path",
            condition=WhenEquals(field="kind", equals="scanned_text"),
        ),
    ]
    if with_escalation:
        transitions.append(
            Transition(from_node_id="clf", to_node_id="rescue", condition=ScoreBelow(threshold=0.5))
        )
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
        Transition(
            from_node_id="clf",
            to_node_id="photo_path",
            condition=WhenEquals(field="kind", equals="photo"),
        )
    )
    codes = {issue.code.value for issue in validator.validate(graph)}
    assert "ambiguous_routing" in codes


def test_when_equals_on_two_fields_is_ambiguous_and_flags_unknown_field(validator) -> None:
    graph = _build("photo")
    graph.transitions.append(
        Transition(
            from_node_id="clf",
            to_node_id="scan_path",
            condition=WhenEquals(field="other", equals="x"),
        )
    )
    codes = {issue.code.value for issue in validator.validate(graph)}
    assert "ambiguous_routing" in codes
    assert "when_equals_unknown_field" in codes


def test_when_equals_condition_round_trips_through_json() -> None:
    transition = Transition(
        from_node_id="a", to_node_id="b", condition=WhenEquals(field="kind", equals="chart")
    )
    again = Transition.model_validate(transition.model_dump(mode="json"))
    assert isinstance(again.condition, WhenEquals)
    assert again.condition.equals == "chart"


# ── the full documented priority chain: ScoreBelow > WhenEquals > OnSuccess/OnFailure > Always ──
#
# `test_score_below_priority_beats_when_equals` above pins the top pair; the rest of the chain is
# pinned here — every remaining (higher, lower) pair, each built so BOTH edges are eligible on the
# same outcome (GraphNavigator.next must pick the higher-ranked one, never fall through to it).


def _switch_group(source: ActionNode, edges: list[Transition]) -> Group:
    """A 2+-node group: one source feeding N candidate targets, wired by the given transitions."""
    targets = {t.to_node_id for t in edges}
    children = [source, *(Path(node_id, NodeConfig(), node_id) for node_id in targets)]
    return Group(id="g", children=children, transitions=edges, bindings={})


def test_score_below_beats_on_success(engine) -> None:
    """A bad score escalates even against a plain OnSuccess edge (not just WhenEquals)."""
    group = _switch_group(
        Classifier("clf", NodeConfig(), kind="photo", score=0.2),
        [
            Transition(
                from_node_id="clf", to_node_id="RESCUE", condition=ScoreBelow(threshold=0.5)
            ),
            Transition(from_node_id="clf", to_node_id="ON-SUCCESS", condition=OnSuccess()),
        ],
    )
    output, _ = asyncio.run(engine.execute(group, {}))
    assert output.tag.value == "RESCUE"


def test_score_below_beats_always(engine) -> None:
    group = _switch_group(
        Classifier("clf", NodeConfig(), kind="photo", score=0.2),
        [
            Transition(
                from_node_id="clf", to_node_id="RESCUE", condition=ScoreBelow(threshold=0.5)
            ),
            Transition(from_node_id="clf", to_node_id="ALWAYS", condition=Always()),
        ],
    )
    output, _ = asyncio.run(engine.execute(group, {}))
    assert output.tag.value == "RESCUE"


def test_when_equals_beats_on_success(engine) -> None:
    group = _switch_group(
        Classifier("clf", NodeConfig(), kind="photo", score=1.0),
        [
            Transition(
                from_node_id="clf",
                to_node_id="PHOTO",
                condition=WhenEquals(field="kind", equals="photo"),
            ),
            Transition(from_node_id="clf", to_node_id="ON-SUCCESS", condition=OnSuccess()),
        ],
    )
    output, _ = asyncio.run(engine.execute(group, {}))
    assert output.tag.value == "PHOTO"


def test_when_equals_beats_always(engine) -> None:
    group = _switch_group(
        Classifier("clf", NodeConfig(), kind="photo", score=1.0),
        [
            Transition(
                from_node_id="clf",
                to_node_id="PHOTO",
                condition=WhenEquals(field="kind", equals="photo"),
            ),
            Transition(from_node_id="clf", to_node_id="ALWAYS", condition=Always()),
        ],
    )
    output, _ = asyncio.run(engine.execute(group, {}))
    assert output.tag.value == "PHOTO"


def test_on_success_beats_always(engine) -> None:
    group = _switch_group(
        Classifier("clf", NodeConfig(), kind="unmatched", score=1.0),
        [
            Transition(from_node_id="clf", to_node_id="ON-SUCCESS", condition=OnSuccess()),
            Transition(from_node_id="clf", to_node_id="ALWAYS", condition=Always()),
        ],
    )
    output, _ = asyncio.run(engine.execute(group, {}))
    assert output.tag.value == "ON-SUCCESS"


def test_on_failure_beats_always(engine) -> None:
    group = _switch_group(
        Failer("clf", NodeConfig()),
        [
            Transition(from_node_id="clf", to_node_id="ON-FAILURE", condition=OnFailure()),
            Transition(from_node_id="clf", to_node_id="ALWAYS", condition=Always()),
        ],
    )
    output, _ = asyncio.run(engine.execute(group, {}))
    assert output.tag.value == "ON-FAILURE"
