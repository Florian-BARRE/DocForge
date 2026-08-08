"""The PP-StructureV3 (PaddleOCR) parser brick — the new sidecar→IR mapper, the HTML-table
flattener, and the network node (_parse over a mocked httpx, preflight, registration).

Everything is offline: the mapper runs over CANNED sidecar responses and the node's httpx client is
monkeypatched, so no live paddle_server is needed. This mirrors how the docling/granite bricks are
tested (no real engine).
"""

import asyncio

import httpx
import pytest
from pydantic import ValidationError

from shared_libs.pipelines.ingest.nodes.parse.parser.base import BaseParserNode
from shared_libs.pipelines.ingest.nodes.parse.parser.pp_structure.config import (
    ParserPpStructureConfig,
)
from shared_libs.pipelines.ingest.nodes.parse.parser.pp_structure.core import ParserPpStructureNode
from shared_libs.pipelines.ingest.nodes.parse.parser.pp_structure.mapper import PpStructureIRMapper
from shared_libs.pipelines.ingest.nodes.parse.parser.pp_structure.table import (
    PpStructureTableFlattener,
)
from shared_libs.pipelines.nodes.openai_compat.preflight import PreflightError
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import BlockType, DocumentIR, IntakeResult

# ==================== canned sidecar responses ====================

_SIMPLE_RESPONSE = {
    "n_pages": 1,
    "engine": {"paddleocr": "3.0.0"},
    "pages": [
        {
            "page_index": 0,
            "image_width": 1000,
            "image_height": 2000,
            "blocks": [
                # Deliberately out of reading order — the mapper must sort by reading_order.
                {
                    "label": "text",
                    "bbox": [100, 300, 900, 400],
                    "text": "Revenue grew 12% year over year and the outlook is positive.",
                    "reading_order": 2,
                },
                {
                    "label": "doc_title",
                    "bbox": [100, 50, 900, 150],
                    "text": "Quarterly Report",
                    "reading_order": 0,
                },
                {
                    "label": "paragraph_title",
                    "bbox": [100, 200, 500, 260],
                    "text": "Revenue",
                    "reading_order": 1,
                },
            ],
        }
    ],
}

_RICH_RESPONSE = {
    "n_pages": 1,
    "pages": [
        {
            "page_index": 0,
            "image_width": 100,
            "image_height": 100,
            "blocks": [
                {
                    "label": "table",
                    "bbox": [0, 0, 100, 20],
                    "html": "<table><tr><th>A</th><th>B</th></tr>"
                    "<tr><td>1</td><td>2</td></tr></table>",
                    "reading_order": 0,
                },
                {
                    "label": "formula",
                    "bbox": [0, 20, 100, 40],
                    "latex": "E=mc^2",
                    "reading_order": 1,
                },
                {"label": "image", "bbox": [50, 50, 100, 100], "reading_order": 2},
                # Unmapped label → skipped, never lands in the IR.
                {"label": "seal", "bbox": [0, 0, 10, 10], "reading_order": 3},
            ],
        }
    ],
}


# ==================== mapper — the simple text/heading case ====================


def test_mapper_maps_labels_reading_order_and_heading_tree() -> None:
    """doc_title/paragraph_title/text map to heading/heading/paragraph, sorted by reading_order,
    with synthesized levels (1, 2) and a heading tree that nests the section under the title."""
    ir: DocumentIR = PpStructureIRMapper.map_response(_SIMPLE_RESPONSE, doc_id="d", source_hash="h")

    assert [b.block_type for b in ir.blocks] == [
        BlockType.HEADING,
        BlockType.HEADING,
        BlockType.PARAGRAPH,
    ]
    assert [b.text for b in ir.blocks] == [
        "Quarterly Report",
        "Revenue",
        "Revenue grew 12% year over year and the outlook is positive.",
    ]
    # Global reading order is a page-major counter, regardless of the per-block source order.
    assert [b.reading_order for b in ir.blocks] == [0, 1, 2]
    # Heading levels are synthesized from the label (doc_title=1, paragraph_title=2).
    title, section, paragraph = ir.blocks
    assert (title.level, section.level) == (1, 2)
    # Heading tree: the section nests under the title; the paragraph under the section.
    assert section.parent_id == title.id
    assert paragraph.parent_id == section.id
    assert ir.n_pages == 1


def test_mapper_normalizes_pixel_bbox_by_the_page_dims_top_left() -> None:
    """A pixel bbox divides by the page-image dims into [0,1] with NO y-flip (top-left origin)."""
    ir = PpStructureIRMapper.map_response(_SIMPLE_RESPONSE, doc_id="d", source_hash="h")
    # doc_title bbox [100,50,900,150] over (1000,2000) → (0.1, 0.025, 0.9, 0.075).
    title = ir.blocks[0]
    assert title.provenance.page == 0
    assert title.provenance.bbox == pytest.approx((0.1, 0.025, 0.9, 0.075))


def test_mapper_bbox_center_lands_at_half() -> None:
    """A bbox at the page centre normalizes to 0.5 — the load-bearing crop-scaling invariant."""
    response = {
        "n_pages": 1,
        "pages": [
            {
                "page_index": 0,
                "image_width": 400,
                "image_height": 800,
                "blocks": [
                    {"label": "text", "bbox": [200, 400, 400, 800], "text": "x", "reading_order": 0}
                ],
            }
        ],
    }
    ir = PpStructureIRMapper.map_response(response, doc_id="d", source_hash="h")
    assert ir.blocks[0].provenance.bbox == pytest.approx((0.5, 0.5, 1.0, 1.0))


def test_mapper_degrades_missing_page_dims_to_full_page() -> None:
    """A zero/missing image dim must not blow up — the block falls back to a full-page box."""
    response = {
        "n_pages": 1,
        "pages": [
            {
                "page_index": 0,
                "image_width": 0,
                "image_height": 0,
                "blocks": [
                    {"label": "text", "bbox": [10, 20, 30, 40], "text": "x", "reading_order": 0}
                ],
            }
        ],
    }
    ir = PpStructureIRMapper.map_response(response, doc_id="d", source_hash="h")
    # dims guarded to 1.0 → the pixel values clamp into [0,1].
    assert ir.blocks[0].provenance.bbox == pytest.approx((1.0, 1.0, 1.0, 1.0))


# ==================== mapper — the table/formula/figure case ====================


def test_mapper_handles_table_formula_figure_and_skips_unmapped() -> None:
    """A table→TableData, a formula→LaTeX text, an image→empty FigureEnrichment, a seal→skipped."""
    ir = PpStructureIRMapper.map_response(_RICH_RESPONSE, doc_id="d", source_hash="h")

    # The unmapped 'seal' block never lands — 3 blocks, not 4.
    assert len(ir.blocks) == 3
    table_block, formula_block, figure_block = ir.blocks

    # 1. Table: flattened into a row-major grid with a header.
    assert table_block.block_type == BlockType.TABLE
    assert table_block.table is not None
    assert table_block.table.cells == [["A", "B"], ["1", "2"]]
    assert (table_block.table.n_rows, table_block.table.n_cols) == (2, 2)
    assert table_block.table.has_header is True

    # 2. Formula: the LaTeX rides in the text slot.
    assert formula_block.block_type == BlockType.FORMULA
    assert formula_block.text == "E=mc^2"

    # 3. Figure: an EMPTY placeholder (crop filled later by figure_render) with its region provenance.
    assert figure_block.block_type == BlockType.FIGURE
    assert figure_block.figure is not None
    assert figure_block.figure.crop is None
    assert figure_block.figure.ocr_text is None
    assert figure_block.provenance.bbox == pytest.approx((0.5, 0.5, 1.0, 1.0))


# ==================== html_to_table — the highest-risk flattener ====================


def test_html_to_table_plain_grid() -> None:
    """A plain grid maps row-major; multi-row grids are treated as headed."""
    table = PpStructureTableFlattener.html_to_table(
        "<table><tr><td>a</td><td>b</td></tr><tr><td>c</td><td>d</td></tr></table>"
    )
    assert table is not None
    assert table.cells == [["a", "b"], ["c", "d"]]
    assert (table.n_rows, table.n_cols) == (2, 2)


def test_html_to_table_thead_marks_header() -> None:
    """A <th> cell flags the table as headed even for a single body row."""
    table = PpStructureTableFlattener.html_to_table(
        "<table><thead><tr><th>H</th></tr></thead><tbody><tr><td>v</td></tr></tbody></table>"
    )
    assert table is not None
    assert table.cells == [["H"], ["v"]]
    assert table.has_header is True


def test_html_to_table_colspan_expands_with_repeat_top_left() -> None:
    """A colspan=2 cell fills its top-left slot and blanks the rest of the span."""
    table = PpStructureTableFlattener.html_to_table(
        "<table><tr><td colspan='2'>x</td></tr><tr><td>a</td><td>b</td></tr></table>"
    )
    assert table is not None
    assert table.cells == [["x", ""], ["a", "b"]]


def test_html_to_table_rowspan_carries_blanks_down() -> None:
    """A rowspan=2 cell keeps its column reserved on the next row (blank), never shifting cells."""
    table = PpStructureTableFlattener.html_to_table(
        "<table><tr><td rowspan='2'>x</td><td>b</td></tr><tr><td>c</td></tr></table>"
    )
    assert table is not None
    assert table.cells == [["x", "b"], ["", "c"]]


def test_html_to_table_combined_row_and_col_span() -> None:
    """A cell spanning 2x2 reserves its whole block; the remaining cells fill around it."""
    table = PpStructureTableFlattener.html_to_table(
        "<table>"
        "<tr><td rowspan='2' colspan='2'>x</td><td>c</td></tr>"
        "<tr><td>f</td></tr>"
        "<tr><td>g</td><td>h</td><td>i</td></tr>"
        "</table>"
    )
    assert table is not None
    assert table.cells == [["x", "", "c"], ["", "", "f"], ["g", "h", "i"]]


def test_html_to_table_degrades_on_empty_or_malformed() -> None:
    """No HTML, empty HTML, or content with no table cells all degrade to None (block drops table)."""
    assert PpStructureTableFlattener.html_to_table(None) is None
    assert PpStructureTableFlattener.html_to_table("   ") is None
    assert PpStructureTableFlattener.html_to_table("just some text, no table") is None


# ==================== node — registration + brick shape ====================


def test_pp_structure_is_registered_under_the_parser_family() -> None:
    """The node self-registers as ('parser', 'pp_structure') and surfaces in the palette."""
    assert NodeRegistry.get("parser", "pp_structure") is ParserPpStructureNode
    assert "pp_structure" in NodeRegistry.kinds("parser")


def test_pp_structure_brick_shape_matches_the_plan() -> None:
    """An off-by-default escalation head: unique, PDF-only, scored, its own Config, no docling base."""
    assert ParserPpStructureNode.KIND == "pp_structure"
    assert ParserPpStructureNode.UNIQUE_IN_GRAPH is True
    assert ParserPpStructureNode.NATIVE_FORMATS == frozenset()
    assert ParserPpStructureNode.Config is ParserPpStructureConfig
    assert issubclass(ParserPpStructureNode, BaseParserNode)
    assert ParserPpStructureNode.describe().scored is True


def test_config_forbids_unknown_fields_and_requires_base_url() -> None:
    """extra='forbid' (via NodeConfig) rejects a typo; base_url has no default."""
    with pytest.raises(ValidationError):
        ParserPpStructureConfig(base_url="http://x:80", do_ocr=True)
    with pytest.raises(ValidationError):
        ParserPpStructureConfig()


def test_config_defaults_lean_toggles() -> None:
    """Lean default: table recognition ON, everything else OFF; no device knob exists."""
    cfg = ParserPpStructureConfig(base_url="http://paddle_server:80")
    assert cfg.use_table_recognition is True
    assert cfg.use_formula_recognition is False
    assert cfg.use_seal_recognition is False
    assert cfg.use_doc_orientation_classify is False
    assert cfg.use_doc_unwarping is False
    assert "device" not in cfg.model_fields


def test_config_strips_whitespace_from_base_url() -> None:
    """A pasted trailing newline is stripped so the HTTP request line stays valid."""
    cfg = ParserPpStructureConfig(base_url="  http://paddle_server:80\n")
    assert cfg.base_url == "http://paddle_server:80"


# ==================== node — _parse over a mocked httpx client ====================


class _FakeResponse:
    """A stand-in httpx.Response carrying a canned JSON body."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def _fake_async_client(*, captured: dict, payload: dict):
    """An httpx.AsyncClient stand-in whose .post() records the call and returns a canned response."""

    class _Client:
        def __init__(self, *args: object, **kwargs: object) -> None:
            captured["init"] = kwargs

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

        async def post(
            self,
            url: str,
            content: bytes | None = None,
            params: dict | None = None,
            headers: dict | None = None,
        ) -> _FakeResponse:
            captured["url"] = url
            captured["content"] = content
            captured["params"] = params
            captured["headers"] = headers
            return _FakeResponse(payload)

    return _Client


def test_parse_posts_the_pdf_and_maps_the_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """_parse POSTs the raw PDF bytes with the knob params and maps the sidecar JSON into an IR."""
    captured: dict = {}
    monkeypatch.setattr(
        httpx, "AsyncClient", _fake_async_client(captured=captured, payload=_RICH_RESPONSE)
    )
    node = ParserPpStructureNode(
        id="p",
        config=ParserPpStructureConfig(base_url="http://paddle_server:80", api_key="tok"),
    )
    source = IntakeResult(source_hash="h", source_format="pdf", pdf_content=b"%PDF-1.7 ...")
    out = asyncio.run(node.run(BaseParserNode.Consumes(source=source)))

    # 1. The raw PDF bytes go in the body with the content-type + bearer + knob params.
    assert captured["url"] == "/layout-parsing"
    assert captured["content"] == b"%PDF-1.7 ..."
    assert captured["headers"]["Content-Type"] == "application/pdf"
    assert captured["headers"]["Authorization"] == "Bearer tok"
    assert captured["params"]["use_table_recognition"] is True
    assert captured["params"]["use_formula_recognition"] is False

    # 2. The mocked response maps into a well-formed IR + a non-zero quality score.
    assert isinstance(out.ir, DocumentIR)
    assert [b.block_type for b in out.ir.blocks] == [
        BlockType.TABLE,
        BlockType.FORMULA,
        BlockType.FIGURE,
    ]
    assert out.score > 0.0  # table + formula carry content


def test_parse_without_a_pdf_view_degrades_to_empty_ir() -> None:
    """No PDF view and no native path (NATIVE_FORMATS empty) → empty IR, score 0, no network call."""
    node = ParserPpStructureNode(
        id="p", config=ParserPpStructureConfig(base_url="http://paddle_server:80")
    )
    source = IntakeResult(source_hash="h", source_format="docx", source_content=b"raw")
    out = asyncio.run(node.run(BaseParserNode.Consumes(source=source)))
    assert out.ir.blocks == []
    assert out.score == 0.0


# ==================== node — preflight ====================


class _ProbeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def _preflight_client(*, status_code: int):
    """An httpx.AsyncClient stand-in for EndpointReachability's GET probe."""

    class _Client:
        def __init__(self, *args: object, **kwargs: object) -> None: ...

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *exc: object) -> None: ...

        async def get(self, url: str, headers: dict | None = None) -> _ProbeResponse:
            return _ProbeResponse(status_code)

    return _Client


def test_preflight_passes_when_health_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any answer on /health (even non-200) proves the sidecar is up — preflight passes."""
    monkeypatch.setattr(httpx, "AsyncClient", _preflight_client(status_code=200))
    node = ParserPpStructureNode(
        id="p", config=ParserPpStructureConfig(base_url="http://paddle_server:80")
    )
    assert asyncio.run(node.preflight()) is None


def test_preflight_fails_on_rejected_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 401 on /health surfaces a rejected bearer token before any spend."""
    monkeypatch.setattr(httpx, "AsyncClient", _preflight_client(status_code=401))
    node = ParserPpStructureNode(
        id="p", config=ParserPpStructureConfig(base_url="http://paddle_server:80", api_key="bad")
    )
    with pytest.raises(PreflightError):
        asyncio.run(node.preflight())
