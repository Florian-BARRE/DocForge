"""The dots.ocr parser brick — the sidecar→IR mapper (against a fixture contract), the network node
(_parse over a mocked httpx, preflight, registration), and its Config.

Everything is offline: the mapper runs over a captured-shape dots.ocr sidecar contract fixture
(``fixtures/dots_ocr_contract.json``), and the node's httpx client is monkeypatched, so no live
dots_ocr_server (GPU-only) is needed. Mirrors how the mineru/paddleocr_vl/pp_structure/docling/granite
bricks are tested (no real engine).
"""

import asyncio
import json
import pathlib

import httpx
import pytest
from pydantic import ValidationError

from shared_libs.pipelines.ingest.nodes.parse.parser.base import BaseParserNode
from shared_libs.pipelines.ingest.nodes.parse.parser.dots_ocr.config import ParserDotsOcrConfig
from shared_libs.pipelines.ingest.nodes.parse.parser.dots_ocr.core import ParserDotsOcrNode
from shared_libs.pipelines.ingest.nodes.parse.parser.dots_ocr.mapper import DotsOcrIRMapper
from shared_libs.pipelines.nodes.openai_compat.preflight import PreflightError
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import BlockType, DocumentIR, IntakeResult

# ==================== the fixture sidecar contract ====================

_CONTRACT = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "dots_ocr_contract.json").read_text()
)


# ==================== mapper — against the fixture contract ====================


def test_mapper_maps_blocks_and_global_reading_order() -> None:
    """Two pages map to IR blocks in a global page-major reading order; a `watermark` label is skipped."""
    ir: DocumentIR = DotsOcrIRMapper.map_response(_CONTRACT, doc_id="d", source_hash="h")

    # 5 blocks (page 0) + 6 mapped blocks (page 1; the `watermark` block is unmapped, skipped).
    assert len(ir.blocks) == 11
    assert ir.n_pages == 2
    # Global reading order is a page-major counter, 0..10 regardless of per-page reading_order.
    assert [b.reading_order for b in ir.blocks] == list(range(11))


def test_mapper_flattens_the_rowspan_table() -> None:
    """The fixture rowspan table flattens to a dense grid; the rowspan cell fills its top-left slot."""
    ir = DotsOcrIRMapper.map_response(_CONTRACT, doc_id="d", source_hash="h")
    table_block = ir.blocks[3]

    assert table_block.block_type == BlockType.TABLE
    assert table_block.table is not None
    assert table_block.table.has_header is True
    # Header row recovered verbatim.
    assert table_block.table.cells[0] == ["Layer", "Complexity"]
    # The rowspan="2" "Recurrent" cell fills its top-left slot; the covered row below it is blank.
    assert table_block.table.cells[2][0] == "Recurrent"
    assert table_block.table.cells[3][0] == ""


def test_mapper_normalizes_bbox_against_actual_page_dims() -> None:
    """A pixel bbox is divided by the page's OWN rendered image dims (non-1000), top-left, no y-flip."""
    ir = DotsOcrIRMapper.map_response(_CONTRACT, doc_id="d", source_hash="h")
    # Page 0 is 2000x1000: [200, 80, 1800, 140] -> (0.10, 0.08, 0.90, 0.14) proves the divisor is the
    # page's real width/height, not a fixed 1000 basis.
    title = ir.blocks[0]
    assert title.provenance.page == 0
    assert title.provenance.bbox == pytest.approx((0.10, 0.08, 0.90, 0.14))
    # Page 1 is 1000x2000: the formula [200, 100, 800, 180] -> (0.20, 0.05, 0.80, 0.09).
    formula = ir.blocks[5]
    assert formula.provenance.page == 1
    assert formula.provenance.bbox == pytest.approx((0.20, 0.05, 0.80, 0.09))


def test_mapper_synthesizes_heading_levels_from_dots_categories() -> None:
    """Title→HEADING L1, Section-header→HEADING L2 (dots.ocr's flat title/section taxonomy)."""
    ir = DotsOcrIRMapper.map_response(_CONTRACT, doc_id="d", source_hash="h")

    title = ir.blocks[0]
    assert title.block_type == BlockType.HEADING
    assert title.level == 1

    section = ir.blocks[2]
    assert section.block_type == BlockType.HEADING
    assert section.level == 2


def test_mapper_maps_picture_to_empty_figure_placeholder() -> None:
    """A Picture block becomes an empty FIGURE placeholder (no text, crop filled by figure_render)."""
    ir = DotsOcrIRMapper.map_response(_CONTRACT, doc_id="d", source_hash="h")
    figures = [b for b in ir.blocks if b.block_type == BlockType.FIGURE]
    assert len(figures) == 1
    assert figures[0].figure is not None
    assert figures[0].figure.crop is None
    assert figures[0].text is None


def test_mapper_maps_list_footnote_and_running_chrome() -> None:
    """List-item→LIST_ITEM, Footnote→PARAGRAPH (content), Page-footer→HEADER_FOOTER (running chrome)."""
    ir = DotsOcrIRMapper.map_response(_CONTRACT, doc_id="d", source_hash="h")
    by_type: dict[BlockType, list] = {}
    for block in ir.blocks:
        by_type.setdefault(block.block_type, []).append(block)

    list_items = by_type[BlockType.LIST_ITEM]
    assert len(list_items) == 1
    assert list_items[0].text == "First bullet point."

    footnote = next(b for b in by_type[BlockType.PARAGRAPH] if b.text.startswith("1. See"))
    assert footnote.block_type == BlockType.PARAGRAPH

    footer = by_type[BlockType.HEADER_FOOTER]
    assert len(footer) == 1
    assert footer[0].text == "Page 2"


def test_mapper_maps_formula_latex_into_text_slot() -> None:
    """A formula block carries its LaTeX in the text slot (chunking treats a formula as text)."""
    ir = DotsOcrIRMapper.map_response(_CONTRACT, doc_id="d", source_hash="h")
    formula = next(b for b in ir.blocks if b.block_type == BlockType.FORMULA)
    assert formula.text.startswith("\\mathrm{Attention}")


# ==================== node — registration + brick shape ====================


def test_dots_ocr_is_registered_under_the_parser_family() -> None:
    """The node self-registers as ('parser', 'dots_ocr') and surfaces in the palette."""
    assert NodeRegistry.get("parser", "dots_ocr") is ParserDotsOcrNode
    assert "dots_ocr" in NodeRegistry.kinds("parser")


def test_dots_ocr_brick_shape_matches_the_plan() -> None:
    """An off-by-default escalation head: unique, PDF-only, scored, its own Config, no docling base."""
    assert ParserDotsOcrNode.KIND == "dots_ocr"
    assert ParserDotsOcrNode.UNIQUE_IN_GRAPH is True
    assert ParserDotsOcrNode.NATIVE_FORMATS == frozenset()
    assert ParserDotsOcrNode.Config is ParserDotsOcrConfig
    assert issubclass(ParserDotsOcrNode, BaseParserNode)
    assert ParserDotsOcrNode.describe().scored is True


# ==================== config ====================


def test_config_forbids_unknown_fields_and_defaults_base_url() -> None:
    """extra='forbid' (via NodeConfig) rejects a typo; base_url defaults to the in-stack sidecar."""
    with pytest.raises(ValidationError):
        ParserDotsOcrConfig(base_url="http://x:80", do_ocr=True)
    assert ParserDotsOcrConfig().base_url == "http://dots_ocr_server:80"


def test_config_defaults_high_timeout_and_no_device_knob() -> None:
    """The VLM timeout defaults high; there is no device knob (deployment concern)."""
    cfg = ParserDotsOcrConfig()
    assert cfg.timeout_seconds == 900.0
    assert "device" not in ParserDotsOcrConfig.model_fields


def test_config_strips_whitespace_from_base_url() -> None:
    """A pasted trailing newline is stripped so the HTTP request line stays valid."""
    cfg = ParserDotsOcrConfig(base_url="  http://dots_ocr_server:80\n")
    assert cfg.base_url == "http://dots_ocr_server:80"


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
            headers: dict | None = None,
        ) -> _FakeResponse:
            captured["url"] = url
            captured["content"] = content
            captured["headers"] = headers
            return _FakeResponse(payload)

    return _Client


def test_parse_posts_the_pdf_and_maps_the_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """_parse POSTs the raw PDF bytes to /parse with the bearer header and maps the sidecar JSON."""
    captured: dict = {}
    monkeypatch.setattr(
        httpx, "AsyncClient", _fake_async_client(captured=captured, payload=_CONTRACT)
    )
    node = ParserDotsOcrNode(
        id="p",
        config=ParserDotsOcrConfig(base_url="http://dots_ocr_server:80", api_key="tok"),
    )
    source = IntakeResult(source_hash="h", source_format="pdf", pdf_content=b"%PDF-1.7 ...")
    out = asyncio.run(node.run(BaseParserNode.Consumes(source=source)))

    # 1. The raw PDF bytes go in the body with the content-type + bearer.
    assert captured["url"] == "/parse"
    assert captured["content"] == b"%PDF-1.7 ..."
    assert captured["headers"]["Content-Type"] == "application/pdf"
    assert captured["headers"]["Authorization"] == "Bearer tok"

    # 2. The mocked response maps into a well-formed IR + a non-zero quality score.
    assert isinstance(out.ir, DocumentIR)
    assert len(out.ir.blocks) == 11
    assert out.score > 0.0


def test_parse_without_a_pdf_view_degrades_to_empty_ir() -> None:
    """No PDF view and no native path (NATIVE_FORMATS empty) → empty IR, score 0, no network call."""
    node = ParserDotsOcrNode(
        id="p", config=ParserDotsOcrConfig(base_url="http://dots_ocr_server:80")
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
    node = ParserDotsOcrNode(
        id="p", config=ParserDotsOcrConfig(base_url="http://dots_ocr_server:80")
    )
    assert asyncio.run(node.preflight()) is None


def test_preflight_fails_on_rejected_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 401 on /health surfaces a rejected bearer token before any spend."""
    monkeypatch.setattr(httpx, "AsyncClient", _preflight_client(status_code=401))
    node = ParserDotsOcrNode(
        id="p", config=ParserDotsOcrConfig(base_url="http://dots_ocr_server:80", api_key="bad")
    )
    with pytest.raises(PreflightError):
        asyncio.run(node.preflight())
