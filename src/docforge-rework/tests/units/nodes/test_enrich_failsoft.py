"""Fail-soft enrich: OnFailure edges -> figure_entry — a flaky figure degrades, the doc SURVIVES.

Ported from the scratchpad's test_enrich_failsoft.py.
"""

import asyncio

import pytest

from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.engine import FlowEngine
from shared_libs.pipelines.ingest.nodes.enrich.figure_classify import FigureClassifyNode
from shared_libs.pipelines.nodes.vlm.base import BaseVlmConfig, BaseVlmNode
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.pipelines.validation import GraphValidator
from shared_libs.public_models import (
    Block,
    BlockType,
    DocumentIR,
    FigureEnrichment,
    FigureKind,
    Provenance,
)


@NodeRegistry.register("enrich")
class FlakyClassify(FigureClassifyNode):
    KIND = "test_enrich_failsoft_flaky_classify"
    NAME = "F"
    SUMMARY = "test"

    async def _ask_model(self, image: bytes, prompt: str) -> str:
        if b"CLF-BOOM" in image:
            raise RuntimeError("classifier endpoint 503")
        return "photo"


@NodeRegistry.register("vlm")
class FlakyVlm(BaseVlmNode):
    KIND = "test_enrich_failsoft_flaky_vlm"
    NAME = "F"
    SUMMARY = "test"
    Config = BaseVlmConfig

    async def _describe(self, image: bytes, context: str, system_prompt: str) -> tuple[str, float]:
        if b"VLM-BOOM" in image:
            raise RuntimeError("vision endpoint 503")
        return "a nice photo", 1.0


def _fig(bid: str, crop: bytes) -> Block:
    return Block(id=bid, block_type=BlockType.FIGURE, reading_order=0,
                 provenance=Provenance(page=0, bbox=(0.2, 0.2, 0.6, 0.6)),
                 figure=FigureEnrichment(crop=crop))


IR = DocumentIR(doc_id="d", source_hash="h", n_pages=1, blocks=[
    _fig("f_ok", b"fine"),            # classify -> photo -> vlm describes
    _fig("f_vlm_boom", b"VLM-BOOM"),  # vlm 503 -> OnFailure -> entry (kind kept, no description)
    _fig("f_clf_boom", b"CLF-BOOM"),  # classify 503 -> OnFailure -> entry (unclassified)
])

BLOB = {
    "node_type": "group", "id": "enrich_failsoft",
    "nodes": [
        {"node_type": "action", "id": "extract", "family": "enrich", "kind": "figure_extract", "config": {}},
        {"node_type": "foreach", "id": "per_figure",
         "over": {"source": "node", "node_id": "extract", "field_name": "figures"},
         "item_field": "figure", "max_concurrency": 2,
         "body": {
             "node_type": "group", "id": "treat",
             "nodes": [
                 {"node_type": "action", "id": "clf", "family": "enrich",
                  "kind": "test_enrich_failsoft_flaky_classify",
                  "config": {"base_url": "http://fake", "model": "m", "use_heuristics": False}},
                 {"node_type": "action", "id": "vlm_photo", "family": "vlm",
                  "kind": "test_enrich_failsoft_flaky_vlm",
                  "config": {"system_prompt": "Caption this photo."}},
                 {"node_type": "action", "id": "fallback_vlm", "family": "enrich",
                  "kind": "figure_entry", "config": {}},
                 {"node_type": "action", "id": "fallback_clf", "family": "enrich",
                  "kind": "figure_entry", "config": {}},
             ],
             "transitions": [
                 {"from_node_id": "clf", "to_node_id": "vlm_photo",
                  "condition": {"kind": "when_equals", "field": "kind", "equals": "photo"}},
                 # FAIL-SOFT: a provider failure ROUTES to a degraded entry instead of failing the doc
                 {"from_node_id": "clf", "to_node_id": "fallback_clf",
                  "condition": {"kind": "on_failure"}},
                 {"from_node_id": "vlm_photo", "to_node_id": "fallback_vlm",
                  "condition": {"kind": "on_failure"}},
             ],
             "bindings": {
                 "clf": {"figure": {"source": "group", "field_name": "figure"}},
                 "vlm_photo": {"figure": {"source": "node", "node_id": "clf", "field_name": "figure"}},
                 "fallback_vlm": {"figure": {"source": "node", "node_id": "clf", "field_name": "figure"}},
                 # clf itself failed -> its figure never existed: fall back to the RAW item
                 "fallback_clf": {"figure": {"source": "group", "field_name": "figure"}},
             },
         }},
        {"node_type": "action", "id": "apply", "family": "enrich", "kind": "enrich_apply", "config": {}},
    ],
    "transitions": [
        {"from_node_id": "extract", "to_node_id": "per_figure"},
        {"from_node_id": "per_figure", "to_node_id": "apply"},
    ],
    "bindings": {
        "extract": {"ir": {"source": "run", "field_name": "ir"}},
        "apply": {"ir": {"source": "run", "field_name": "ir"},
                  "entries": {"source": "node", "node_id": "per_figure", "field_name": "items"}},
    },
}


def test_failsoft_blob_validates_clean_with_onfailure_edges() -> None:
    """OnFailure fallbacks are ordinary graph edges — no special validation carve-out needed."""
    group = PipelineBuilder().build(BLOB)
    assert GraphValidator().validate(group) == []


@pytest.fixture(scope="module")
def run_result():
    """Run the whole fail-soft scenario ONCE (sync fixture wrapping asyncio.run)."""
    group = PipelineBuilder().build(BLOB)
    output, record = asyncio.run(FlowEngine().execute(group, {"ir": IR}))
    assert output is not None, record.error  # <-- THE point: the document SUCCEEDS
    figures = {block.id: block.figure for block in output.ir.figure_blocks}
    return output, record, figures


def test_healthy_figure_is_fully_enriched(run_result) -> None:
    _output, _record, figures = run_result
    assert figures["f_ok"].kind == FigureKind.PHOTO
    assert figures["f_ok"].description == "a nice photo"


def test_vlm_failure_degrades_but_keeps_the_classified_kind(run_result) -> None:
    _output, _record, figures = run_result
    assert figures["f_vlm_boom"].kind == FigureKind.PHOTO
    assert figures["f_vlm_boom"].description is None


def test_classify_failure_leaves_the_parse_time_slot_untouched(run_result) -> None:
    _output, _record, figures = run_result
    assert figures["f_clf_boom"].description is None
    assert figures["f_clf_boom"].ocr_text is None


def test_trace_still_shows_both_failures_and_their_fallbacks(run_result) -> None:
    _output, record, _figures = run_result
    foreach_record = next(r for r in record.children if r.node_id == "per_figure")
    vlm_item = foreach_record.children[1]
    statuses = {child.node_id: child.status.value for child in vlm_item.children}
    assert statuses["vlm_photo"] == "failed"
    assert statuses["fallback_vlm"] == "success"
    clf_item = foreach_record.children[2]
    statuses = {child.node_id: child.status.value for child in clf_item.children}
    assert statuses["clf"] == "failed"
    assert statuses["fallback_clf"] == "success"
