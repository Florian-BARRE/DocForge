"""Knob A — the per-figure enrich loop's max_concurrency is read from the enrich stage config.

``figure_concurrency`` threads blob -> PipelineState (StateReader) -> the assembled per_figure
ForEach, defaulting to 4 when a stored blob omits it (no migration, no break). Raising it
parallelises the paid VLM/OCR calls for image-heavy docs.

The plumbing tests below only prove the NUMBER flows through unmutated; ``test_concurrency_is_
enforced_at_runtime_by_the_engine`` proves the number actually BOUNDS the engine's real execution
(a live semaphore around ``asyncio.gather``, not just a stored int) — see
``FlowEngine.__collect_foreach_items`` in ``shared_libs/pipelines/engine/core.py``.
"""

import asyncio

from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.build.blob import ForEachNodeBlob
from shared_libs.pipelines.ingest.stages import IngestAssembler, StateReader, default_state
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.pipelines.validation import GraphValidator
from shared_libs.public_models import Artifact


def _per_figure(blob) -> ForEachNodeBlob:
    """The assembled enrich loop node."""
    return next(n for n in blob.nodes if isinstance(n, ForEachNodeBlob) and n.id == "per_figure")


def _enrich_state(**overrides):
    """The stock state with enrich turned on (it ships off) plus any overrides."""
    return default_state().model_copy(update={"enrich_on": True, **overrides})


def test_figure_concurrency_flows_from_state_into_the_per_figure_loop() -> None:
    blob = IngestAssembler.assemble(_enrich_state(figure_concurrency=8))
    assert _per_figure(blob).max_concurrency == 8


def test_default_figure_concurrency_is_four() -> None:
    blob = IngestAssembler.assemble(_enrich_state())
    assert _per_figure(blob).max_concurrency == 4


def test_figure_concurrency_round_trips_through_the_reader() -> None:
    blob = IngestAssembler.assemble(_enrich_state(figure_concurrency=8))
    assert StateReader.read(blob).figure_concurrency == 8


def test_blob_omitting_concurrency_reads_back_as_four() -> None:
    """A stored blob whose ForEach carries the default max_concurrency reads back as 4 — no break."""
    blob = IngestAssembler.assemble(_enrich_state())
    assert StateReader.read(blob).figure_concurrency == 4


def test_raised_concurrency_still_validates_clean() -> None:
    blob = IngestAssembler.assemble(_enrich_state(figure_concurrency=16))
    assert GraphValidator().validate(PipelineBuilder().build(blob)) == []


# ── runtime enforcement — a real ForEach graph, executed by the real engine ────────────────────


class _Item(Artifact):
    index: int = 0


class _ItemsOut(NodeOutput):
    items: list[_Item]


class _TrackedOut(NodeOutput):
    item: _Item


class _ItemIn(NodeInput):
    item: _Item


# Shared mutable concurrency probe — reset per test, read back after the run.
_CONCURRENCY_PROBE = {"active": 0, "peak": 0}


@NodeRegistry.register("test_concurrency_family")
class _ProduceItems(ActionNode):
    """Emits a fixed-size list of items for the ForEach to iterate over."""

    KIND = "test_concurrency_produce"
    NAME = "Produce"
    SUMMARY = "s"
    Config = NodeConfig

    class Consumes(NodeInput):
        pass

    Produces = _ItemsOut

    async def run(self, data) -> "_ItemsOut":
        return self.Produces(items=[_Item(index=i) for i in range(6)])


@NodeRegistry.register("test_concurrency_family")
class _TrackConcurrency(ActionNode):
    """Records how many sibling item-runs are in flight at once, peaking the shared probe."""

    KIND = "test_concurrency_track"
    NAME = "Track"
    SUMMARY = "s"
    Config = NodeConfig
    Consumes = _ItemIn
    Produces = _TrackedOut

    async def run(self, data: _ItemIn) -> "_TrackedOut":
        _CONCURRENCY_PROBE["active"] += 1
        _CONCURRENCY_PROBE["peak"] = max(_CONCURRENCY_PROBE["peak"], _CONCURRENCY_PROBE["active"])
        try:
            # Yield control so sibling item-runs actually get a chance to overlap — without this
            # await, the cooperative scheduler would run each item to completion before the next,
            # masking a broken (unbounded) semaphore just as easily as a correctly bounded one.
            await asyncio.sleep(0.01)
        finally:
            _CONCURRENCY_PROBE["active"] -= 1
        return self.Produces(item=data.item)


def _concurrency_blob(max_concurrency: int) -> dict:
    """A minimal ForEach graph: produce 6 items, track peak in-flight runs over the body."""
    return {
        "node_type": "group",
        "id": "root",
        "nodes": [
            {
                "node_type": "action",
                "id": "produce",
                "family": "test_concurrency_family",
                "kind": "test_concurrency_produce",
                "config": {},
            },
            {
                "node_type": "foreach",
                "id": "per_item",
                "over": {"source": "node", "node_id": "produce", "field_name": "items"},
                "item_field": "item",
                "max_concurrency": max_concurrency,
                "body": {
                    "node_type": "group",
                    "id": "track",
                    "nodes": [
                        {
                            "node_type": "action",
                            "id": "track",
                            "family": "test_concurrency_family",
                            "kind": "test_concurrency_track",
                            "config": {},
                        }
                    ],
                    "transitions": [],
                    "bindings": {
                        "track": {"item": {"source": "group", "field_name": "item"}},
                    },
                },
            },
        ],
        "transitions": [{"from_node_id": "produce", "to_node_id": "per_item"}],
        "bindings": {},
    }


def test_concurrency_is_enforced_at_runtime_by_the_engine(builder, engine) -> None:
    """The engine never runs more than max_concurrency item-subgraphs at once — nor fewer.

    Two assertions in one run: peak in-flight runs must not EXCEED the bound (the semaphore does
    its job), and must actually REACH it (proving the bound isn't accidentally serializing
    everything down to 1, which would pass a naive "<=" check for the wrong reason).
    """
    _CONCURRENCY_PROBE["active"] = 0
    _CONCURRENCY_PROBE["peak"] = 0
    group = builder.build(_concurrency_blob(max_concurrency=3))

    asyncio.run(engine.execute(group, {}))

    assert _CONCURRENCY_PROBE["peak"] == 3


def test_concurrency_of_one_runs_strictly_serially(builder, engine) -> None:
    """max_concurrency=1 is the degenerate case: peak in-flight must never exceed 1."""
    _CONCURRENCY_PROBE["active"] = 0
    _CONCURRENCY_PROBE["peak"] = 0
    group = builder.build(_concurrency_blob(max_concurrency=1))

    asyncio.run(engine.execute(group, {}))

    assert _CONCURRENCY_PROBE["peak"] == 1
