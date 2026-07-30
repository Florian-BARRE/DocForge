"""VLM quality-escalation: a scored VlmProduces + a ScoreBelow edge escalate to the next provider,
the branch closing on the model-free vlm_entry terminal fed best-first — the OCR pattern, for VLM.

A low-confidence description on the first (cheap) provider escalates to the second (robust) one; a
high-confidence description closes the branch directly. Both paths converge on a single-slot
{entry} terminal, keeping the ForEach body contract intact.
"""

import asyncio

import shared_libs.pipelines.ingest.nodes  # noqa: F401 — registers ingest + enrich nodes
import shared_libs.pipelines.nodes  # noqa: F401 — registers generic families (vlm)
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.engine import FlowEngine
from shared_libs.pipelines.nodes.vlm.base import BaseVlmConfig, BaseVlmNode
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.pipelines.validation import GraphValidator
from shared_libs.public_models import (
    Block,
    BlockType,
    DocumentIR,
    FigureEnrichment,
    Provenance,
)

CALLS = {"vlm_cheap": 0, "vlm_robust": 0}


@NodeRegistry.register("vlm")
class FakeVlmCheap(BaseVlmNode):
    KIND = "test_vlm_esc_cheap"
    NAME = "F"
    SUMMARY = "test"
    Config = BaseVlmConfig

    async def _describe(self, image: bytes, context: str, system_prompt: str) -> tuple[str, float]:
        CALLS["vlm_cheap"] += 1
        # A hard figure yields a low-confidence description → escalation; an easy one is accepted.
        if b"HARD" in image:
            return "blurry guess", 0.2
        return f"cheap desc of {image[:9].decode()}", 0.9


@NodeRegistry.register("vlm")
class FakeVlmRobust(BaseVlmNode):
    KIND = "test_vlm_esc_robust"
    NAME = "F"
    SUMMARY = "test"
    Config = BaseVlmConfig

    async def _describe(self, image: bytes, context: str, system_prompt: str) -> tuple[str, float]:
        CALLS["vlm_robust"] += 1
        return "ROBUST DESC", 0.95


def _fig(bid: str, crop: bytes, order: int) -> Block:
    return Block(
        id=bid,
        block_type=BlockType.FIGURE,
        reading_order=order,
        provenance=Provenance(page=0, bbox=(0.2, 0.2, 0.6, 0.6)),
        figure=FigureEnrichment(crop=crop),
    )


IR = DocumentIR(
    doc_id="d",
    source_hash="h",
    n_pages=1,
    blocks=[
        _fig("f_easy", b"EASY-fig-", 0),  # cheap accepted (0.9)
        _fig("f_hard", b"HARD-fig-", 1),  # cheap rejected (0.2) -> escalate to robust
    ],
)


BLOB = {
    "node_type": "group",
    "id": "vlm_esc_stage",
    "nodes": [
        {
            "node_type": "action",
            "id": "extract",
            "family": "enrich",
            "kind": "figure_extract",
            "config": {},
        },
        {
            "node_type": "foreach",
            "id": "per_figure",
            "over": {"source": "node", "node_id": "extract", "field_name": "figures"},
            "item_field": "figure",
            "max_concurrency": 2,
            "body": {
                "node_type": "group",
                "id": "treat",
                "nodes": [
                    {
                        "node_type": "action",
                        "id": "vlm_cheap",
                        "family": "vlm",
                        "kind": "test_vlm_esc_cheap",
                        "config": {},
                    },
                    {
                        "node_type": "action",
                        "id": "vlm_robust",
                        "family": "vlm",
                        "kind": "test_vlm_esc_robust",
                        "config": {},
                    },
                    {
                        "node_type": "action",
                        "id": "v_entry",
                        "family": "enrich",
                        "kind": "vlm_entry",
                        "config": {},
                    },
                ],
                "transitions": [
                    # ScoreBelow > OnSuccess: a low-confidence cheap description escalates, else it closes.
                    {
                        "from_node_id": "vlm_cheap",
                        "to_node_id": "vlm_robust",
                        "condition": {"kind": "score_below", "threshold": 0.5},
                    },
                    {"from_node_id": "vlm_cheap", "to_node_id": "v_entry"},
                    {"from_node_id": "vlm_robust", "to_node_id": "v_entry"},
                ],
                "bindings": {
                    "vlm_cheap": {"figure": {"source": "group", "field_name": "figure"}},
                    "vlm_robust": {"figure": {"source": "group", "field_name": "figure"}},
                    "v_entry": {
                        "entry": {
                            "source": "first",
                            "candidates": [
                                {"source": "node", "node_id": "vlm_robust", "field_name": "entry"},
                                {"source": "node", "node_id": "vlm_cheap", "field_name": "entry"},
                            ],
                        }
                    },
                },
            },
        },
        {
            "node_type": "action",
            "id": "apply",
            "family": "enrich",
            "kind": "enrich_apply",
            "config": {},
        },
    ],
    "transitions": [
        {"from_node_id": "extract", "to_node_id": "per_figure"},
        {"from_node_id": "per_figure", "to_node_id": "apply"},
    ],
    "bindings": {
        "extract": {"ir": {"source": "run", "field_name": "ir"}},
        "apply": {
            "ir": {"source": "run", "field_name": "ir"},
            "entries": {"source": "node", "node_id": "per_figure", "field_name": "items"},
        },
    },
}


def test_vlm_escalation_blob_builds_and_validates_clean() -> None:
    """The ScoreBelow edge off a VLM step + the vlm_entry single-slot terminals validate clean."""
    group = PipelineBuilder().build(BLOB)
    assert GraphValidator().validate(group) == []


def _run():
    CALLS["vlm_cheap"] = 0
    CALLS["vlm_robust"] = 0
    group = PipelineBuilder().build(BLOB)
    output, record = asyncio.run(FlowEngine().execute(group, {"ir": IR}))
    assert output is not None, record.error
    figures = {block.id: block.figure for block in output.ir.figure_blocks}
    return figures


def test_high_confidence_vlm_closes_the_branch_directly() -> None:
    """A single-VLM path (cheap accepted): the branch closes on vlm_entry, no escalation."""
    figures = _run()
    assert figures["f_easy"].description == "cheap desc of EASY-fig-"
    assert CALLS["vlm_robust"] == 1  # robust ran only for the hard figure


def test_low_confidence_vlm_escalates_then_closes_on_vlm_entry() -> None:
    """A low-confidence cheap description escalates via score_below to the robust provider, whose
    description is the one the vlm_entry terminal carries (best-first join)."""
    figures = _run()
    assert figures["f_hard"].description == "ROBUST DESC"
