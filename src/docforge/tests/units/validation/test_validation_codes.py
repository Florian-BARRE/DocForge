"""Every GraphValidator check fires on the graph that should trigger it, and stays silent on a
healthy one. Ported from the scratchpad's test_validation.py (structural + binding codes; the
WhenEquals-specific codes live in tests/units/engine/test_conditions.py, foreach-specific ones in
tests/units/validation/test_foreach_validation.py, duplicate-unique in test_duplicate_unique.py).
"""

from enum import StrEnum

from shared_libs.pipelines.base import (
    ActionNode,
    FromNode,
    Group,
    NodeConfig,
    NodeInput,
    NodeOutput,
    ScoreBelow,
    Transition,
    WhenEquals,
)
from shared_libs.pipelines.ingest import IngestPipeline  # noqa: F401 — registers the llm family
from shared_libs.pipelines.validation import GraphInvalidError
from shared_libs.public_models import Artifact


class Cfg(NodeConfig):
    pass


class Doc(Artifact):
    text: str = ""


class Other(Artifact):
    v: int = 0


class Empty(NodeInput):
    pass


class DocOut(NodeOutput):
    doc: Doc


class DocIn(NodeInput):
    doc: Doc


class OtherIn(NodeInput):
    item: Other


class Producer(ActionNode):
    KIND = "test_validation_producer"
    NAME = "P"
    SUMMARY = "s"
    Config = Cfg
    Consumes = Empty
    Produces = DocOut

    async def run(self, data):
        return DocOut(doc=Doc())


class ConsumerDoc(ActionNode):
    KIND = "test_validation_consumer_doc"
    NAME = "CD"
    SUMMARY = "s"
    Config = Cfg
    Consumes = DocIn
    Produces = DocOut

    async def run(self, data):
        return DocOut(doc=data.doc)


class ConsumerOther(ActionNode):
    KIND = "test_validation_consumer_other"
    NAME = "CO"
    SUMMARY = "s"
    Config = Cfg
    Consumes = OtherIn
    Produces = DocOut

    async def run(self, data):
        return DocOut(doc=Doc())


class Flavor(StrEnum):
    A = "a"
    B = "b"
    C = "c"


class KindedOut(NodeOutput):
    kind: Flavor = Flavor.A


class Switch(ActionNode):
    KIND = "test_validation_switch"
    NAME = "SW"
    SUMMARY = "s"
    Config = Cfg
    Consumes = Empty
    Produces = KindedOut
    SWITCH_FIELDS = {"kind": [flavor.value for flavor in Flavor]}

    async def run(self, data):
        return KindedOut()


def _p(node_id: str) -> Producer:
    return Producer(id=node_id, config=Cfg())


def _cd(node_id: str) -> ConsumerDoc:
    return ConsumerDoc(id=node_id, config=Cfg())


def _codes(validator, group) -> set[str]:
    return {issue.code.value for issue in validator.validate(group)}


def test_valid_sequence_has_zero_issues(validator) -> None:
    graph = Group(
        id="ok",
        children=[_p("a"), _cd("b")],
        transitions=[Transition(from_node_id="a", to_node_id="b")],
        bindings={"a": {}, "b": {"doc": FromNode(node_id="a", field_name="doc")}},
    )
    assert _codes(validator, graph) == set()


def test_type_mismatch(validator) -> None:
    graph = Group(
        id="tm",
        children=[_p("a"), ConsumerOther(id="b", config=Cfg())],
        transitions=[Transition(from_node_id="a", to_node_id="b")],
        bindings={"a": {}, "b": {"item": FromNode(node_id="a", field_name="doc")}},
    )
    assert "type_mismatch" in _codes(validator, graph)


def test_missing_binding_on_required_slot(validator) -> None:
    graph = Group(
        id="mb",
        children=[_p("a"), _cd("b")],
        transitions=[Transition(from_node_id="a", to_node_id="b")],
        bindings={"a": {}},
    )
    assert "missing_binding" in _codes(validator, graph)


def test_binding_not_upstream(validator) -> None:
    graph = Group(
        id="up",
        children=[_p("a"), _cd("b"), _p("c")],
        transitions=[
            Transition(from_node_id="a", to_node_id="b"),
            Transition(from_node_id="b", to_node_id="c"),
        ],
        bindings={"a": {}, "b": {"doc": FromNode(node_id="c", field_name="doc")}, "c": {}},
    )
    assert "binding_not_upstream" in _codes(validator, graph)


def test_unknown_slot_binding_is_flagged(validator) -> None:
    """A binding to a slot the action node does NOT declare is a wiring typo. The resolver reads
    only declared slots, so it would silently ignore it — the validator must surface it instead."""
    graph = Group(
        id="us",
        children=[_p("a"), _cd("b")],
        transitions=[Transition(from_node_id="a", to_node_id="b")],
        bindings={
            "a": {},
            "b": {
                "doc": FromNode(node_id="a", field_name="doc"),
                "typo_slot": FromNode(node_id="a", field_name="doc"),
            },
        },
    )
    codes = _codes(validator, graph)
    assert "unknown_slot" in codes


def test_only_declared_slots_bound_raises_no_unknown_slot(validator) -> None:
    """The healthy sequence (only the declared slot bound) raises no unknown_slot issue."""
    graph = Group(
        id="ks",
        children=[_p("a"), _cd("b")],
        transitions=[Transition(from_node_id="a", to_node_id="b")],
        bindings={"a": {}, "b": {"doc": FromNode(node_id="a", field_name="doc")}},
    )
    assert "unknown_slot" not in _codes(validator, graph)


def test_cycle_detected(validator) -> None:
    graph = Group(
        id="cy",
        children=[_cd("a"), _cd("b")],
        transitions=[
            Transition(from_node_id="a", to_node_id="b"),
            Transition(from_node_id="b", to_node_id="a"),
        ],
        bindings={
            "a": {"doc": FromNode(node_id="b", field_name="doc")},
            "b": {"doc": FromNode(node_id="a", field_name="doc")},
        },
    )
    assert "cycle" in _codes(validator, graph)


def test_no_single_entry_with_no_transitions(validator) -> None:
    graph = Group(id="ne", children=[_p("a"), _p("b")], bindings={"a": {}, "b": {}})
    assert "no_single_entry" in _codes(validator, graph)


def test_no_single_entry_on_empty_group(validator) -> None:
    """An EMPTY group (zero nodes) is a defect too — nothing would ever run."""
    graph = Group(id="empty", children=[])
    assert "no_single_entry" in _codes(validator, graph)


def test_unknown_node_in_transition(validator) -> None:
    graph = Group(
        id="un",
        children=[_p("a")],
        transitions=[Transition(from_node_id="a", to_node_id="z")],
        bindings={"a": {}},
    )
    assert "unknown_node" in _codes(validator, graph)


def test_score_below_from_unscored_producer(validator) -> None:
    graph = Group(
        id="sc",
        children=[_p("a"), _p("b")],
        transitions=[
            Transition(from_node_id="a", to_node_id="b", condition=ScoreBelow(threshold=0.5))
        ],
        bindings={"a": {}, "b": {}},
    )
    assert "score_below_not_scored" in _codes(validator, graph)


def test_score_below_off_a_vlm_node_is_valid(builder, validator) -> None:
    """A VLM provider is scored (VlmProduces subclasses ScoredOutput), so a ScoreBelow escalation
    edge off it is accepted — the enabler for VLM quality-escalation chains."""
    blob = {
        "node_type": "group",
        "id": "vlm_esc",
        "nodes": [
            {
                "node_type": "action",
                "id": "cheap",
                "family": "vlm",
                "kind": "openai_compatible",
                "config": {"base_url": "u", "model": "m"},
            },
            {
                "node_type": "action",
                "id": "robust",
                "family": "vlm",
                "kind": "openai_compatible",
                "config": {"base_url": "u", "model": "m"},
            },
        ],
        "transitions": [
            {
                "from_node_id": "cheap",
                "to_node_id": "robust",
                "condition": {"kind": "score_below", "threshold": 0.5},
            },
        ],
        "bindings": {
            "cheap": {"figure": {"source": "run", "field_name": "figure"}},
            "robust": {"figure": {"source": "run", "field_name": "figure"}},
        },
    }
    assert validator.validate(builder.build(blob)) == []


def test_unknown_producer_field(validator) -> None:
    graph = Group(
        id="uf",
        children=[_p("a"), _cd("b")],
        transitions=[Transition(from_node_id="a", to_node_id="b")],
        bindings={"a": {}, "b": {"doc": FromNode(node_id="a", field_name="nope")}},
    )
    assert "unknown_field" in _codes(validator, graph)


def test_escalation_pilot_blob_is_valid(builder, validator) -> None:
    blob = {
        "node_type": "group",
        "id": "esc",
        "nodes": [
            {
                "node_type": "action",
                "id": "mistral",
                "family": "llm",
                "kind": "mistral",
                "config": {"api_key": "k"},
            },
            {
                "node_type": "action",
                "id": "openai",
                "family": "llm",
                "kind": "openai_compatible",
                "config": {"base_url": "u", "api_key": "k", "model": "m"},
            },
        ],
        "transitions": [
            {"from_node_id": "mistral", "to_node_id": "openai", "condition": {"kind": "on_failure"}}
        ],
        "bindings": {
            "mistral": {"prompt": {"source": "run", "field_name": "prompt"}},
            "openai": {"prompt": {"source": "run", "field_name": "prompt"}},
        },
    }
    assert validator.validate(builder.build(blob)) == []


def test_validate_or_raise_raises_with_every_issue(validator) -> None:
    graph = Group(id="bad", children=[_p("a"), _p("b")])
    try:
        validator.validate_or_raise(graph)
        raise AssertionError("expected GraphInvalidError")
    except GraphInvalidError as exc:
        assert len(exc.issues) >= 1


# ── switch exhaustiveness (SWITCH_NOT_EXHAUSTIVE) ────────────────────────────────────────────────


def test_switch_not_exhaustive_without_default_fires(validator) -> None:
    """A closed switch missing a value and lacking an OnSuccess/Always default is rejected."""
    graph = Group(
        id="sw",
        children=[Switch(id="s", config=Cfg()), _p("a"), _p("b")],
        bindings={"s": {}, "a": {}, "b": {}},
        transitions=[
            Transition(
                from_node_id="s", to_node_id="a", condition=WhenEquals(field="kind", equals="a")
            ),
            Transition(
                from_node_id="s", to_node_id="b", condition=WhenEquals(field="kind", equals="b")
            ),
        ],
    )
    assert "switch_not_exhaustive" in _codes(validator, graph)


def test_switch_not_exhaustive_with_a_single_edge_fires(validator) -> None:
    """A LONE WhenEquals edge on a closed switch field with no default is still non-exhaustive:
    at run time every unmatched value silently ends the group as SUCCESS. Before the fix the
    exhaustiveness check was skipped entirely for a single WhenEquals edge, so this passed."""
    graph = Group(
        id="sw",
        children=[Switch(id="s", config=Cfg()), _p("a")],
        bindings={"s": {}, "a": {}},
        transitions=[
            Transition(
                from_node_id="s", to_node_id="a", condition=WhenEquals(field="kind", equals="a")
            ),
        ],
    )
    assert "switch_not_exhaustive" in _codes(validator, graph)


def test_switch_with_default_edge_is_valid(validator) -> None:
    """A partial switch WITH a default (bare OnSuccess) edge routes unmatched values → no issue."""
    graph = Group(
        id="sw",
        children=[Switch(id="s", config=Cfg()), _p("a"), _p("b"), _p("d")],
        bindings={"s": {}, "a": {}, "b": {}, "d": {}},
        transitions=[
            Transition(
                from_node_id="s", to_node_id="a", condition=WhenEquals(field="kind", equals="a")
            ),
            Transition(
                from_node_id="s", to_node_id="b", condition=WhenEquals(field="kind", equals="b")
            ),
            Transition(from_node_id="s", to_node_id="d"),  # bare = OnSuccess default
        ],
    )
    assert "switch_not_exhaustive" not in _codes(validator, graph)


def test_switch_full_coverage_is_valid(validator) -> None:
    """A switch covering every declared value needs no default → no issue."""
    graph = Group(
        id="sw",
        children=[Switch(id="s", config=Cfg()), _p("a"), _p("b"), _p("c")],
        bindings={"s": {}, "a": {}, "b": {}, "c": {}},
        transitions=[
            Transition(
                from_node_id="s", to_node_id="a", condition=WhenEquals(field="kind", equals="a")
            ),
            Transition(
                from_node_id="s", to_node_id="b", condition=WhenEquals(field="kind", equals="b")
            ),
            Transition(
                from_node_id="s", to_node_id="c", condition=WhenEquals(field="kind", equals="c")
            ),
        ],
    )
    assert "switch_not_exhaustive" not in _codes(validator, graph)
