"""The PaddleOCR-VL 1.6 parser brick — the sidecar→IR mapper (against a REAL captured sample), the
network node (_parse over a mocked httpx, preflight, registration), and its Config.

Everything is offline: the mapper runs over the captured PaddleOCR-VL sidecar contract fixture
(``fixtures/paddleocr_vl_contract.json``, normalized from a real two-page PaddleOCR-VL 1.6 capture —
attention.pdf p8 with a rowspan table + multifig.pdf p0 with images), and the node's httpx client is
monkeypatched, so no live paddle_server is needed. Mirrors how the pp_structure/docling/granite
bricks are tested (no real engine).
"""

import asyncio
import json
import pathlib

import httpx
import pytest
from pydantic import ValidationError

from shared_libs.pipelines.ingest.nodes.parse.parser.base import BaseParserNode
from shared_libs.pipelines.ingest.nodes.parse.parser.paddleocr_vl.config import (
    ParserPaddleOcrVlConfig,
)
from shared_libs.pipelines.ingest.nodes.parse.parser.paddleocr_vl.core import ParserPaddleOcrVlNode
from shared_libs.pipelines.ingest.nodes.parse.parser.paddleocr_vl.mapper import PaddleOcrVlIRMapper
from shared_libs.pipelines.nodes.openai_compat.preflight import PreflightError
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import BlockType, DocumentIR, IntakeResult

# ==================== the real captured sidecar contract ====================

_CONTRACT = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "paddleocr_vl_contract.json").read_text()
)

# A tiny canned contract for the _parse network test (a table + a formula + an image + an unmapped
# label), independent of the big captured fixture.
_RICH_RESPONSE = {
    "n_pages": 1,
    "engine": {"paddleocr": "3.7.0", "pipeline": "PaddleOCR-VL-v1.6"},
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
                {"label": "image", "bbox": [50, 50, 100, 100], "text": "", "reading_order": 2},
                # Unmapped label → skipped, never lands in the IR.
                {"label": "seal", "bbox": [0, 0, 10, 10], "reading_order": 3},
            ],
        }
    ],
}


# ==================== mapper — against the REAL captured sample ====================


def test_mapper_maps_the_real_captured_sample_blocks_and_reading_order() -> None:
    """The two captured pages map to 21 IR blocks in a global page-major reading order, each label
    resolved to its BlockType (figure_title→CAPTION, image→FIGURE, number→PARAGRAPH)."""
    ir: DocumentIR = PaddleOcrVlIRMapper.map_response(_CONTRACT, doc_id="d", source_hash="h")

    # 10 blocks (page A) + 11 blocks (page B) — every captured label is mapped, none skipped.
    assert len(ir.blocks) == 21
    assert ir.n_pages == 2
    # Global reading order is a page-major counter, 0..20 regardless of per-page reading_order.
    assert [b.reading_order for b in ir.blocks] == list(range(21))

    # Page A opens with the table's caption (figure_title→CAPTION), then the table.
    assert ir.blocks[0].block_type == BlockType.CAPTION
    assert ir.blocks[0].text.startswith("Table 3:")
    assert ir.blocks[1].block_type == BlockType.TABLE


def test_mapper_flattens_the_real_rowspan_table() -> None:
    """The captured transformer table (rowspan cells, LaTeX in cells) flattens to a dense 21×13 grid
    with a header; a rowspan label lands in its top-left covered cell."""
    ir = PaddleOcrVlIRMapper.map_response(_CONTRACT, doc_id="d", source_hash="h")
    table_block = ir.blocks[1]

    assert table_block.table is not None
    assert (table_block.table.n_rows, table_block.table.n_cols) == (21, 13)
    assert table_block.table.has_header is True
    # Header row + the first data row are recovered verbatim (LaTeX cells kept as source).
    assert table_block.table.cells[0][1] == "N"
    assert table_block.table.cells[1][0] == "base"
    # A rowspan="4" "(A)" cell fills its top-left slot; the covered rows below it are blank.
    assert table_block.table.cells[2][0] == "(A)"
    assert table_block.table.cells[3][0] == ""


def test_mapper_normalizes_pixel_bbox_by_the_page_dims_top_left() -> None:
    """A captured pixel bbox divides by the page-image dims into [0,1] with NO y-flip."""
    ir = PaddleOcrVlIRMapper.map_response(_CONTRACT, doc_id="d", source_hash="h")
    # figure_title bbox [209,140,1013,231] over (1224,1584).
    caption = ir.blocks[0]
    assert caption.provenance.page == 0
    assert caption.provenance.bbox == pytest.approx(
        (209 / 1224, 140 / 1584, 1013 / 1224, 231 / 1584)
    )


def test_mapper_synthesizes_headings_and_figures_from_the_sample() -> None:
    """doc_title→HEADING level 1, paragraph_title→HEADING level 2, image→empty FIGURE placeholder."""
    ir = PaddleOcrVlIRMapper.map_response(_CONTRACT, doc_id="d", source_hash="h")

    # The doc_title opens page B (global index 10, right after page A's 10 blocks).
    doc_title = ir.blocks[10]
    assert doc_title.block_type == BlockType.HEADING
    assert doc_title.level == 1
    assert doc_title.text == "Multi-Figure Report"

    # Every paragraph_title is a level-2 heading.
    section_headings = [b for b in ir.blocks if b.block_type == BlockType.HEADING and b.level == 2]
    assert len(section_headings) == 4  # "6.3 English..." + Section 1/2/3

    # The two image blocks are empty FIGURE placeholders (crop filled later by figure_render).
    figures = [b for b in ir.blocks if b.block_type == BlockType.FIGURE]
    assert len(figures) == 2
    for fig in figures:
        assert fig.figure is not None
        assert fig.figure.crop is None


# ==================== mapper — the table/formula/figure/skip case ====================


def test_mapper_handles_table_formula_figure_and_skips_unmapped() -> None:
    """A table→TableData, a formula→LaTeX text, an image→empty FigureEnrichment, a seal→skipped."""
    ir = PaddleOcrVlIRMapper.map_response(_RICH_RESPONSE, doc_id="d", source_hash="h")

    # The unmapped 'seal' block never lands — 3 blocks, not 4.
    assert len(ir.blocks) == 3
    table_block, formula_block, figure_block = ir.blocks

    assert table_block.block_type == BlockType.TABLE
    assert table_block.table is not None
    assert table_block.table.cells == [["A", "B"], ["1", "2"]]
    assert table_block.table.has_header is True

    assert formula_block.block_type == BlockType.FORMULA
    assert formula_block.text == "E=mc^2"

    assert figure_block.block_type == BlockType.FIGURE
    assert figure_block.figure is not None
    assert figure_block.figure.crop is None
    assert figure_block.provenance.bbox == pytest.approx((0.5, 0.5, 1.0, 1.0))


# ==================== node — registration + brick shape ====================


def test_paddleocr_vl_is_registered_under_the_parser_family() -> None:
    """The node self-registers as ('parser', 'paddleocr_vl') and surfaces in the palette."""
    assert NodeRegistry.get("parser", "paddleocr_vl") is ParserPaddleOcrVlNode
    assert "paddleocr_vl" in NodeRegistry.kinds("parser")


def test_paddleocr_vl_brick_shape_matches_the_plan() -> None:
    """An off-by-default escalation head: unique, PDF-only, scored, its own Config, no docling base."""
    assert ParserPaddleOcrVlNode.KIND == "paddleocr_vl"
    assert ParserPaddleOcrVlNode.UNIQUE_IN_GRAPH is True
    assert ParserPaddleOcrVlNode.NATIVE_FORMATS == frozenset()
    assert ParserPaddleOcrVlNode.Config is ParserPaddleOcrVlConfig
    assert issubclass(ParserPaddleOcrVlNode, BaseParserNode)
    assert ParserPaddleOcrVlNode.describe().scored is True


# ==================== config ====================


def test_config_forbids_unknown_fields_and_defaults_base_url() -> None:
    """extra='forbid' (via NodeConfig) rejects a typo; base_url defaults to the in-stack sidecar."""
    with pytest.raises(ValidationError):
        ParserPaddleOcrVlConfig(base_url="http://x:80", do_ocr=True)
    assert ParserPaddleOcrVlConfig().base_url == "http://paddle_server:80"


def test_config_defaults_lean_toggles_and_high_timeout() -> None:
    """Lean default: every heavy sub-pipeline OFF; the VLM timeout defaults high; no device knob."""
    cfg = ParserPaddleOcrVlConfig()
    assert cfg.use_chart_recognition is False
    assert cfg.use_seal_recognition is False
    assert cfg.use_ocr_for_image_block is False
    assert cfg.timeout_seconds == 600.0
    assert "device" not in cfg.model_fields


def test_config_strips_whitespace_from_base_url() -> None:
    """A pasted trailing newline is stripped so the HTTP request line stays valid."""
    cfg = ParserPaddleOcrVlConfig(base_url="  http://paddle_server:80\n")
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
    """_parse POSTs the raw PDF bytes to /vl-parse with the knob params and maps the sidecar JSON."""
    captured: dict = {}
    monkeypatch.setattr(
        httpx, "AsyncClient", _fake_async_client(captured=captured, payload=_RICH_RESPONSE)
    )
    node = ParserPaddleOcrVlNode(
        id="p",
        config=ParserPaddleOcrVlConfig(base_url="http://paddle_server:80", api_key="tok"),
    )
    source = IntakeResult(source_hash="h", source_format="pdf", pdf_content=b"%PDF-1.7 ...")
    out = asyncio.run(node.run(BaseParserNode.Consumes(source=source)))

    # 1. The raw PDF bytes go in the body with the content-type + bearer + knob params.
    assert captured["url"] == "/vl-parse"
    assert captured["content"] == b"%PDF-1.7 ..."
    assert captured["headers"]["Content-Type"] == "application/pdf"
    assert captured["headers"]["Authorization"] == "Bearer tok"
    assert captured["params"]["use_chart_recognition"] is False
    assert captured["params"]["use_seal_recognition"] is False
    assert captured["params"]["use_ocr_for_image_block"] is False

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
    node = ParserPaddleOcrVlNode(
        id="p", config=ParserPaddleOcrVlConfig(base_url="http://paddle_server:80")
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
    node = ParserPaddleOcrVlNode(
        id="p", config=ParserPaddleOcrVlConfig(base_url="http://paddle_server:80")
    )
    assert asyncio.run(node.preflight()) is None


def test_preflight_fails_on_rejected_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 401 on /health surfaces a rejected bearer token before any spend."""
    monkeypatch.setattr(httpx, "AsyncClient", _preflight_client(status_code=401))
    node = ParserPaddleOcrVlNode(
        id="p", config=ParserPaddleOcrVlConfig(base_url="http://paddle_server:80", api_key="bad")
    )
    with pytest.raises(PreflightError):
        asyncio.run(node.preflight())
