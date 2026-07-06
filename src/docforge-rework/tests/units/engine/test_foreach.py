"""ForEach execution: per-item switch routing, ordering, concurrency, runtime failures.

Ported from the scratchpad's test_foreach.py (execution half; validator-code assertions live in
tests/units/validation/test_foreach_validation.py).
"""

import asyncio

import pytest
from pydantic import Field

from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import Artifact


class Thing(Artifact):
    kind_value: str = ""
    payload: str = ""


class Entry(Artifact):
    label: str = ""


class Merged(Artifact):
    labels: list[str] = Field(default_factory=list)


class ThingIn(NodeInput):
    thing: Thing


@NodeRegistry.register("test_foreach_family")
class Extract(ActionNode):
    KIND = "test_foreach_extract"
    NAME = "E"
    SUMMARY = "s"
    Config = NodeConfig

    class Consumes(NodeInput):
        pass

    class Produces(NodeOutput):
        things: list[Thing]
        note: str = ""

    async def run(self, data) -> "Extract.Produces":
        return self.Produces(things=list(RUN_THINGS), note="not-a-list")


@NodeRegistry.register("test_foreach_family")
class Classify(ActionNode):
    KIND = "test_foreach_classify"
    NAME = "C"
    SUMMARY = "s"
    Config = NodeConfig
    Consumes = ThingIn

    class Produces(NodeOutput):
        kind: str

    async def run(self, data: ThingIn) -> "Classify.Produces":
        return self.Produces(kind=data.thing.kind_value)


class PathConfig(NodeConfig):
    label: str


@NodeRegistry.register("test_foreach_family")
class PathNode(ActionNode):
    KIND = "test_foreach_path"
    NAME = "P"
    SUMMARY = "s"
    Config = PathConfig
    Consumes = ThingIn

    class Produces(NodeOutput):
        entry: Entry

    async def run(self, data: ThingIn) -> "PathNode.Produces":
        if data.thing.payload == "boom":
            raise RuntimeError("provider exploded")
        config: PathConfig = self.config
        return self.Produces(entry=Entry(label=f"{config.label}:{data.thing.payload}"))


@NodeRegistry.register("test_foreach_family")
class Collect(ActionNode):
    KIND = "test_foreach_collect"
    NAME = "K"
    SUMMARY = "s"
    Config = NodeConfig

    class Consumes(NodeInput):
        entries: list[Entry]

    class Produces(NodeOutput):
        merged: Merged

    async def run(self, data) -> "Collect.Produces":
        return self.Produces(merged=Merged(labels=[e.label for e in data.entries]))


RUN_THINGS: list[Thing] = []


def _blob() -> dict:
    return {
        "node_type": "group",
        "id": "root",
        "nodes": [
            {"node_type": "action", "id": "extract", "family": "test_foreach_family", "kind": "test_foreach_extract", "config": {}},
            {
                "node_type": "foreach",
                "id": "per_thing",
                "over": {"source": "node", "node_id": "extract", "field_name": "things"},
                "item_field": "thing",
                "max_concurrency": 2,
                "body": {
                    "node_type": "group",
                    "id": "treat",
                    "nodes": [
                        {"node_type": "action", "id": "clf", "family": "test_foreach_family", "kind": "test_foreach_classify", "config": {}},
                        {"node_type": "action", "id": "photo", "family": "test_foreach_family", "kind": "test_foreach_path", "config": {"label": "PHOTO"}},
                        {"node_type": "action", "id": "scan", "family": "test_foreach_family", "kind": "test_foreach_path", "config": {"label": "SCAN"}},
                        {"node_type": "action", "id": "skip", "family": "test_foreach_family", "kind": "test_foreach_path", "config": {"label": "SKIP"}},
                    ],
                    "transitions": [
                        {"from_node_id": "clf", "to_node_id": "photo", "condition": {"kind": "when_equals", "field": "kind", "equals": "photo"}},
                        {"from_node_id": "clf", "to_node_id": "scan", "condition": {"kind": "when_equals", "field": "kind", "equals": "scanned_text"}},
                        {"from_node_id": "clf", "to_node_id": "skip", "condition": {"kind": "when_equals", "field": "kind", "equals": "decorative"}},
                    ],
                    "bindings": {
                        "clf": {"thing": {"source": "group", "field_name": "thing"}},
                        "photo": {"thing": {"source": "group", "field_name": "thing"}},
                        "scan": {"thing": {"source": "group", "field_name": "thing"}},
                        "skip": {"thing": {"source": "group", "field_name": "thing"}},
                    },
                },
            },
            {"node_type": "action", "id": "collect", "family": "test_foreach_family", "kind": "test_foreach_collect", "config": {}},
        ],
        "transitions": [
            {"from_node_id": "extract", "to_node_id": "per_thing"},
            {"from_node_id": "per_thing", "to_node_id": "collect"},
        ],
        "bindings": {
            "collect": {"entries": {"source": "node", "node_id": "per_thing", "field_name": "items"}},
        },
    }


@pytest.fixture
def group(builder: PipelineBuilder):
    return builder.build(_blob())


def test_build_and_validate_is_clean(group, validator) -> None:
    assert validator.validate(group) == []


def test_per_item_switch_routing_preserves_order(group, engine) -> None:
    global RUN_THINGS
    RUN_THINGS = [
        Thing(kind_value="photo", payload="p1"),
        Thing(kind_value="scanned_text", payload="s1"),
        Thing(kind_value="decorative", payload="logo"),
        Thing(kind_value="photo", payload="p2"),
    ]
    output, record = asyncio.run(engine.execute(group, {}))
    assert output.merged.labels == ["PHOTO:p1", "SCAN:s1", "SKIP:logo", "PHOTO:p2"]
    fe_record = next(r for r in record.children if r.node_id == "per_thing")
    assert [c.node_id for c in fe_record.children] == ["treat[0]", "treat[1]", "treat[2]", "treat[3]"]
    assert all(c.status.value == "success" for c in fe_record.children)


def test_empty_list_yields_empty_items(group, engine) -> None:
    global RUN_THINGS
    RUN_THINGS = []
    output, _ = asyncio.run(engine.execute(group, {}))
    assert output.merged.labels == []


def test_item_provider_crash_fails_the_foreach_loudly(group, engine) -> None:
    global RUN_THINGS
    RUN_THINGS = [Thing(kind_value="photo", payload="boom")]
    output, record = asyncio.run(engine.execute(group, {}))
    loop_record = next(r for r in record.children if r.node_id == "per_thing")
    assert output is None
    assert loop_record.status.value == "failed"
    assert "item 0 failed" in loop_record.error.message


def test_off_contract_early_stop_fails_the_foreach_loudly(group, engine) -> None:
    """An unmatched switch value inside the body stops before the uniform terminal is reached."""
    global RUN_THINGS
    RUN_THINGS = [Thing(kind_value="unknown_kind", payload="x")]
    output, record = asyncio.run(engine.execute(group, {}))
    loop_record = next(r for r in record.children if r.node_id == "per_thing")
    assert output is None
    assert "must end on the body's terminal artefact" in loop_record.error.message
