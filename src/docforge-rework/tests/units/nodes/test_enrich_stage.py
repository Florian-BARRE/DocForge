"""Enrich stage e2e: extract -> ForEach[classify -> switch x5 -> branches] -> apply, via blob.

Ported from the scratchpad's test_enrich_stage.py. The whole scenario (7 figures, one engine
run) is expensive to re-run per assertion, so it executes ONCE in a module-scoped fixture and
each test asserts one facet of the single trace/result — mirroring how the scratchpad narrates
it, just split into independently-reportable pytest failures.
"""

import struct

import pytest

import shared_libs.pipelines.ingest.nodes  # noqa: F401 — registers ingest + enrich nodes
import shared_libs.pipelines.nodes  # noqa: F401 — registers generic families (ocr/vlm)
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.engine import FlowEngine
from shared_libs.pipelines.ingest.nodes.enrich.figure_classify import FigureClassifyNode
from shared_libs.pipelines.nodes.ocr.base import BaseOcrConfig, BaseOcrNode
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

CALLS = {"classify_model": 0, "ocr_cheap": 0, "ocr_robust": 0, "vlm": 0}


@NodeRegistry.register("enrich")
class FakeClassify(FigureClassifyNode):
    KIND = "test_enrich_stage_classify"
    NAME = "Fake classify"
    SUMMARY = "test"

    async def _ask_model(self, image: bytes, prompt: str) -> str:
        CALLS["classify_model"] += 1
        for marker, kind in ((b"PHOTO", "photo"), (b"CHART", "chart"), (b"DIAGRAM", "diagram")):
            if image.startswith(marker):
                return kind
        return "???"


@NodeRegistry.register("ocr")
class FakeOcrCheap(BaseOcrNode):
    KIND = "test_enrich_stage_ocr_cheap"
    NAME = "F"
    SUMMARY = "test"
    Config = BaseOcrConfig

    async def _read(self, image: bytes) -> tuple[str, float]:
        CALLS["ocr_cheap"] += 1
        if b"HARD" in image:
            return "g@rb1ed", 0.2
        return f"cheap read of {image[:9].decode()}", 0.9


@NodeRegistry.register("ocr")
class FakeOcrRobust(BaseOcrNode):
    KIND = "test_enrich_stage_ocr_robust"
    NAME = "F"
    SUMMARY = "test"
    Config = BaseOcrConfig

    async def _read(self, image: bytes) -> tuple[str, float]:
        CALLS["ocr_robust"] += 1
        return "ROBUST READ", 0.95


@NodeRegistry.register("vlm")
class FakeVlm(BaseVlmNode):
    KIND = "test_enrich_stage_vlm"
    NAME = "F"
    SUMMARY = "test"
    Config = BaseVlmConfig

    async def _describe(self, image: bytes, context: str, system_prompt: str) -> tuple[str, float]:
        CALLS["vlm"] += 1
        # The node prepends an always-on anti-deflection guard before the per-class prompt. Echo
        # the per-class first line (after the guard separator) so class-specific assertions hold,
        # plus a flag proving the guard reached the prompt (locks the FIX-1 invariant).
        guard_ok = "NEVER ask for more" in system_prompt
        per_class = system_prompt.split("\n\n", 1)[-1].splitlines()[0][:80]
        answer = f"DESC[{'guard+' if guard_ok else 'NOGUARD+'}{per_class}|ctx={context or '-'}]"
        if "```table" in system_prompt:
            answer += "\n```table\nX | Y\n1 | 2\n```"
        return answer, 1.0


def _fig_block(bid: str, crop: bytes | None, bbox=(0.2, 0.2, 0.6, 0.6), order: int = 0) -> Block:
    return Block(
        id=bid,
        block_type=BlockType.FIGURE,
        reading_order=order,
        provenance=Provenance(page=0, bbox=bbox),
        figure=FigureEnrichment(crop=crop) if crop is not None else None,
    )


TINY_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + struct.pack(">II", 10, 10) + b"\x00" * 5

IR = DocumentIR(
    doc_id="d1",
    source_hash="h",
    n_pages=1,
    blocks=[
        _fig_block(
            "f_scan", b"EASY-SCAN", bbox=(0.0, 0.0, 1.0, 1.0), order=0
        ),  # heuristic: full page
        _fig_block(
            "f_hard", b"HARD-SCAN", bbox=(0.0, 0.0, 1.0, 1.0), order=1
        ),  # full page + hard OCR
        _fig_block("f_photo", b"PHOTO-cat", order=2),
        _fig_block("f_chart", b"CHART-rev", order=3),
        _fig_block("f_diag", b"DIAGRAM-a", order=4),
        _fig_block("f_deco", TINY_PNG, order=5),  # heuristic: tiny
        _fig_block("f_nocrop", None, order=6),  # nothing to enrich
    ],
)

CLF_CONFIG = {"base_url": "http://fake", "model": "fake-clf"}


def _vlm(node_id: str, prompt: str, extract_table: bool = False) -> dict:
    return {
        "node_type": "action",
        "id": node_id,
        "family": "vlm",
        "kind": "test_enrich_stage_vlm",
        "config": {"system_prompt": prompt, "extract_table": extract_table},
    }


BLOB = {
    "node_type": "group",
    "id": "enrich_stage",
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
            "max_concurrency": 3,
            "body": {
                "node_type": "group",
                "id": "treat",
                "nodes": [
                    {
                        "node_type": "action",
                        "id": "clf",
                        "family": "enrich",
                        "kind": "test_enrich_stage_classify",
                        "config": CLF_CONFIG,
                    },
                    {
                        "node_type": "action",
                        "id": "ocr_cheap",
                        "family": "ocr",
                        "kind": "test_enrich_stage_ocr_cheap",
                        "config": {},
                    },
                    {
                        "node_type": "action",
                        "id": "ocr_robust",
                        "family": "ocr",
                        "kind": "test_enrich_stage_ocr_robust",
                        "config": {},
                    },
                    _vlm("vlm_scan", "Complement this scan for retrieval."),
                    _vlm("vlm_photo", "Caption this photo."),
                    _vlm("vlm_chart", "Read this chart.", extract_table=True),
                    _vlm("vlm_diag", "Rewrite this diagram as searchable text."),
                    # A VLM produces a SCORED entry ({entry, score}); the model-free vlm_entry projects
                    # it onto the uniform single-slot {entry} terminal every branch converges on.
                    {
                        "node_type": "action",
                        "id": "vs_entry",
                        "family": "enrich",
                        "kind": "vlm_entry",
                        "config": {},
                    },
                    {
                        "node_type": "action",
                        "id": "vp_entry",
                        "family": "enrich",
                        "kind": "vlm_entry",
                        "config": {},
                    },
                    {
                        "node_type": "action",
                        "id": "vc_entry",
                        "family": "enrich",
                        "kind": "vlm_entry",
                        "config": {},
                    },
                    {
                        "node_type": "action",
                        "id": "vd_entry",
                        "family": "enrich",
                        "kind": "vlm_entry",
                        "config": {},
                    },
                    {
                        "node_type": "action",
                        "id": "skip",
                        "family": "enrich",
                        "kind": "figure_entry",
                        "config": {},
                    },
                ],
                "transitions": [
                    {
                        "from_node_id": "clf",
                        "to_node_id": "ocr_cheap",
                        "condition": {
                            "kind": "when_equals",
                            "field": "kind",
                            "equals": "scanned_text",
                        },
                    },
                    {
                        "from_node_id": "clf",
                        "to_node_id": "vlm_photo",
                        "condition": {"kind": "when_equals", "field": "kind", "equals": "photo"},
                    },
                    {
                        "from_node_id": "clf",
                        "to_node_id": "vlm_chart",
                        "condition": {"kind": "when_equals", "field": "kind", "equals": "chart"},
                    },
                    {
                        "from_node_id": "clf",
                        "to_node_id": "vlm_diag",
                        "condition": {"kind": "when_equals", "field": "kind", "equals": "diagram"},
                    },
                    {
                        "from_node_id": "clf",
                        "to_node_id": "skip",
                        "condition": {
                            "kind": "when_equals",
                            "field": "kind",
                            "equals": "decorative",
                        },
                    },
                    {
                        "from_node_id": "ocr_cheap",
                        "to_node_id": "ocr_robust",
                        "condition": {"kind": "score_below", "threshold": 0.5},
                    },
                    {"from_node_id": "ocr_cheap", "to_node_id": "vlm_scan"},
                    {"from_node_id": "ocr_robust", "to_node_id": "vlm_scan"},
                    {"from_node_id": "vlm_scan", "to_node_id": "vs_entry"},
                    {"from_node_id": "vlm_photo", "to_node_id": "vp_entry"},
                    {"from_node_id": "vlm_chart", "to_node_id": "vc_entry"},
                    {"from_node_id": "vlm_diag", "to_node_id": "vd_entry"},
                ],
                "bindings": {
                    "clf": {"figure": {"source": "group", "field_name": "figure"}},
                    "ocr_cheap": {
                        "figure": {"source": "node", "node_id": "clf", "field_name": "figure"}
                    },
                    "ocr_robust": {
                        "figure": {"source": "node", "node_id": "clf", "field_name": "figure"}
                    },
                    "vlm_scan": {
                        "figure": {
                            "source": "first",
                            "candidates": [
                                {"source": "node", "node_id": "ocr_robust", "field_name": "figure"},
                                {"source": "node", "node_id": "ocr_cheap", "field_name": "figure"},
                            ],
                        }
                    },
                    "vlm_photo": {
                        "figure": {"source": "node", "node_id": "clf", "field_name": "figure"}
                    },
                    "vlm_chart": {
                        "figure": {"source": "node", "node_id": "clf", "field_name": "figure"}
                    },
                    "vlm_diag": {
                        "figure": {"source": "node", "node_id": "clf", "field_name": "figure"}
                    },
                    "vs_entry": {
                        "entry": {"source": "node", "node_id": "vlm_scan", "field_name": "entry"}
                    },
                    "vp_entry": {
                        "entry": {"source": "node", "node_id": "vlm_photo", "field_name": "entry"}
                    },
                    "vc_entry": {
                        "entry": {"source": "node", "node_id": "vlm_chart", "field_name": "entry"}
                    },
                    "vd_entry": {
                        "entry": {"source": "node", "node_id": "vlm_diag", "field_name": "entry"}
                    },
                    "skip": {
                        "figure": {"source": "node", "node_id": "clf", "field_name": "figure"}
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


def test_enrich_stage_blob_builds_and_validates_clean() -> None:
    """FromFirst join, switch x5, and 5 uniform terminals all validate with 0 issues."""
    group = PipelineBuilder().build(BLOB)
    assert GraphValidator().validate(group) == []


@pytest.fixture(scope="module")
def run_result():
    """Run the whole enrich scenario ONCE (sync fixture wrapping asyncio.run — avoids any
    module/function event-loop scope mismatch with pytest-asyncio's function-scoped default).
    """
    import asyncio

    group = PipelineBuilder().build(BLOB)
    output, record = asyncio.run(FlowEngine().execute(group, {"ir": IR}))
    assert output is not None, record.error
    figures = {block.id: block.figure for block in output.ir.figure_blocks}
    return output, record, figures


def test_scanned_easy_figure_gets_heuristic_kind_and_cheap_ocr(run_result) -> None:
    _output, _record, figures = run_result
    assert figures["f_scan"].kind == FigureKind.SCANNED_TEXT
    assert figures["f_scan"].ocr_text == "cheap read of EASY-SCAN"
    assert "ctx=cheap read of EASY-SCAN" in figures["f_scan"].description


def test_scanned_hard_figure_escalates_via_score_below(run_result) -> None:
    _output, _record, figures = run_result
    assert figures["f_hard"].ocr_text == "ROBUST READ"
    assert "ctx=ROBUST READ" in figures["f_hard"].description


def test_photo_chart_diagram_get_class_specific_treatment(run_result) -> None:
    _output, _record, figures = run_result
    assert figures["f_photo"].kind == FigureKind.PHOTO
    # The anti-deflection guard is prepended to EVERY figure prompt (node invariant, FIX 1)...
    assert figures["f_photo"].description.startswith("DESC[guard+")
    # ...ahead of the still-distinct per-class prompt.
    assert "Caption this photo" in figures["f_photo"].description
    assert figures["f_photo"].ocr_text is None
    assert figures["f_chart"].kind == FigureKind.CHART
    assert figures["f_chart"].data_table == [["X", "Y"], ["1", "2"]]
    assert "```" not in figures["f_chart"].description
    assert figures["f_diag"].kind == FigureKind.DIAGRAM
    assert "Rewrite" in figures["f_diag"].description


def test_decorative_figure_uses_heuristic_and_spends_nothing(run_result) -> None:
    _output, _record, figures = run_result
    assert figures["f_deco"].kind == FigureKind.DECORATIVE
    assert figures["f_deco"].description is None
    assert figures["f_deco"].ocr_text is None


def test_cropless_block_is_left_untouched(run_result) -> None:
    _output, _record, figures = run_result
    assert figures["f_nocrop"] is None


def test_spend_accounting_heuristics_saved_three_model_calls(run_result) -> None:
    assert CALLS == {"classify_model": 3, "ocr_cheap": 2, "ocr_robust": 1, "vlm": 5}


def test_trace_shows_the_hard_scan_escalation(run_result) -> None:
    _output, record, _figures = run_result
    foreach_record = next(r for r in record.children if r.node_id == "per_figure")
    assert len(foreach_record.children) == 6
    hard_item = foreach_record.children[1]  # item order == figure order
    steps = [(child.node_id, child.status.value) for child in hard_item.children]
    assert ("ocr_cheap", "success") in steps
    assert ("ocr_robust", "success") in steps
