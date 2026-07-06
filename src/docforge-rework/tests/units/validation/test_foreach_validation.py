"""ForEach-specific validator rules: foreach_invalid_body, 'over' type mismatch, items unknown_field.

Ported from the scratchpad's test_foreach.py (validator section).
"""

from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import Artifact


class Thing(Artifact):
    kind_value: str = ""
    payload: str = ""


class Entry(Artifact):
    label: str = ""


class ThingIn(NodeInput):
    thing: Thing


@NodeRegistry.register("test_fev_family")
class Extract(ActionNode):
    KIND = "test_fev_extract"
    NAME = "E"
    SUMMARY = "s"
    Config = NodeConfig

    class Consumes(NodeInput):
        pass

    class Produces(NodeOutput):
        things: list[Thing]
        note: str = ""

    async def run(self, data):
        return self.Produces(things=[], note="not-a-list")


@NodeRegistry.register("test_fev_family")
class Classify(ActionNode):
    KIND = "test_fev_classify"
    NAME = "C"
    SUMMARY = "s"
    Config = NodeConfig
    Consumes = ThingIn

    class Produces(NodeOutput):
        kind: str

    async def run(self, data):
        return self.Produces(kind=data.thing.kind_value)


@NodeRegistry.register("test_fev_family")
class Rogue(ActionNode):
    """Reachable terminal whose Produces is NOT the uniform Entry — breaks the body contract."""

    KIND = "test_fev_rogue"
    NAME = "R"
    SUMMARY = "s"
    Config = NodeConfig
    Consumes = ThingIn

    class Produces(NodeOutput):
        kind: str

    async def run(self, data):
        return self.Produces(kind="rogue")


@NodeRegistry.register("test_fev_family")
class PathTerminal(ActionNode):
    KIND = "test_fev_path"
    NAME = "P"
    SUMMARY = "s"
    Config = NodeConfig
    Consumes = ThingIn

    class Produces(NodeOutput):
        entry: Entry

    async def run(self, data):
        return self.Produces(entry=Entry(label="x"))


@NodeRegistry.register("test_fev_family")
class Collect(ActionNode):
    KIND = "test_fev_collect"
    NAME = "K"
    SUMMARY = "s"
    Config = NodeConfig

    class Consumes(NodeInput):
        entries: list[Entry]

    class Produces(NodeOutput):
        merged: list[str]

    async def run(self, data):
        return self.Produces(merged=[e.label for e in data.entries])


def _blob(bad_terminal: bool = False, over_field: str = "things", collect_slot_type_ok: bool = True) -> dict:
    body_nodes = [
        {"node_type": "action", "id": "clf", "family": "test_fev_family", "kind": "test_fev_classify", "config": {}},
        {"node_type": "action", "id": "photo", "family": "test_fev_family", "kind": "test_fev_path", "config": {}},
    ]
    extra_transitions = []
    if bad_terminal:
        body_nodes.append(
            {"node_type": "action", "id": "rogue", "family": "test_fev_family", "kind": "test_fev_rogue", "config": {}}
        )
        extra_transitions.append(
            {
                "from_node_id": "clf",
                "to_node_id": "rogue",
                "condition": {"kind": "when_equals", "field": "kind", "equals": "rogue"},
            }
        )
    return {
        "node_type": "group",
        "id": "root",
        "nodes": [
            {"node_type": "action", "id": "extract", "family": "test_fev_family", "kind": "test_fev_extract", "config": {}},
            {
                "node_type": "foreach",
                "id": "per_thing",
                "over": {"source": "node", "node_id": "extract", "field_name": over_field},
                "item_field": "thing",
                "max_concurrency": 2,
                "body": {
                    "node_type": "group",
                    "id": "treat",
                    "nodes": body_nodes,
                    "transitions": [
                        {
                            "from_node_id": "clf",
                            "to_node_id": "photo",
                            "condition": {"kind": "when_equals", "field": "kind", "equals": "photo"},
                        },
                        *extra_transitions,
                    ],
                    "bindings": {
                        "clf": {"thing": {"source": "group", "field_name": "thing"}},
                        "photo": {"thing": {"source": "group", "field_name": "thing"}},
                    },
                },
            },
            {"node_type": "action", "id": "collect", "family": "test_fev_family", "kind": "test_fev_collect", "config": {}},
        ],
        "transitions": [
            {"from_node_id": "extract", "to_node_id": "per_thing"},
            {"from_node_id": "per_thing", "to_node_id": "collect"},
        ],
        "bindings": {
            "collect": {
                "entries": {
                    "source": "node",
                    "node_id": "per_thing",
                    "field_name": "items" if collect_slot_type_ok else "nope",
                }
            },
        },
    }


def _codes(builder: PipelineBuilder, validator, blob: dict) -> set[str]:
    return {issue.code.value for issue in validator.validate(builder.build(blob))}


def test_non_uniform_terminal_is_foreach_invalid_body(builder, validator) -> None:
    assert "foreach_invalid_body" in _codes(builder, validator, _blob(bad_terminal=True))


def test_over_on_a_non_list_field_is_type_mismatch(builder, validator) -> None:
    assert "type_mismatch" in _codes(builder, validator, _blob(over_field="note"))


def test_consuming_a_non_items_foreach_field_is_unknown_field(builder, validator) -> None:
    assert "unknown_field" in _codes(builder, validator, _blob(collect_slot_type_ok=False))


def test_healthy_foreach_blob_has_zero_issues(builder, validator) -> None:
    assert _codes(builder, validator, _blob()) == set()
