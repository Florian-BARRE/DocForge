"""The MinerU2.5-Pro parser brick — the sidecar→IR mapper (against a fixture contract), the network
node (_parse over a mocked httpx, preflight, registration), and its Config.

Everything is offline: the mapper runs over a captured-shape MinerU sidecar contract fixture
(``fixtures/mineru_contract.json``), and the node's httpx client is monkeypatched, so no live
mineru_server (GPU-only) is needed. Mirrors how the paddleocr_vl/pp_structure/docling/granite bricks
are tested (no real engine).
"""

import asyncio
import json
import pathlib

import httpx
import pytest
from pydantic import ValidationError

from shared_libs.pipelines.ingest.nodes.parse.parser.base import BaseParserNode
from shared_libs.pipelines.ingest.nodes.parse.parser.mineru.config import ParserMineruConfig
from shared_libs.pipelines.ingest.nodes.parse.parser.mineru.core import ParserMineruNode
from shared_libs.pipelines.ingest.nodes.parse.parser.mineru.mapper import MineruIRMapper
from shared_libs.pipelines.nodes.openai_compat.preflight import PreflightError
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import BlockType, DocumentIR, IntakeResult

# ==================== the fixture sidecar contract ====================

_CONTRACT = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "mineru_contract.json").read_text()
)


# ==================== mapper — against the fixture contract ====================


def test_mapper_maps_blocks_and_global_reading_order() -> None:
    """The two pages map to IR blocks in a global page-major reading order; a `seal` label is skipped."""
    ir: DocumentIR = MineruIRMapper.map_response(_CONTRACT, doc_id="d", source_hash="h")

    # 5 blocks (page 0) + 3 mapped blocks (page 1; the `seal` block is unmapped, skipped).
    assert len(ir.blocks) == 8
    assert ir.n_pages == 2
    # Global reading order is a page-major counter, 0..7 regardless of per-page reading_order.
    assert [b.reading_order for b in ir.blocks] == list(range(8))


def test_mapper_flattens_the_rowspan_table() -> None:
    """The fixture rowspan table flattens to a dense grid; the rowspan cell fills its top-left slot."""
    ir = MineruIRMapper.map_response(_CONTRACT, doc_id="d", source_hash="h")
    table_block = ir.blocks[3]

    assert table_block.block_type == BlockType.TABLE
    assert table_block.table is not None
    assert table_block.table.has_header is True
    # Header row recovered verbatim.
    assert table_block.table.cells[0] == ["Layer", "Complexity"]
    # The rowspan="2" "Recurrent" cell fills its top-left slot; the covered row below it is blank.
    assert table_block.table.cells[2][0] == "Recurrent"
    assert table_block.table.cells[3][0] == ""


def test_mapper_normalizes_bbox_into_unit_range() -> None:
    """A 0–1000 bbox over image dims 1000 normalizes into [0, 1] with NO y-flip."""
    ir = MineruIRMapper.map_response(_CONTRACT, doc_id="d", source_hash="h")
    title = ir.blocks[0]
    assert title.provenance.page == 0
    assert title.provenance.bbox == pytest.approx((0.10, 0.08, 0.90, 0.14))


def test_mapper_synthesizes_heading_levels_and_figures() -> None:
    """title→HEADING L1, paragraph_title→L2, subsection→L3; image→empty FIGURE placeholder."""
    ir = MineruIRMapper.map_response(_CONTRACT, doc_id="d", source_hash="h")

    title = ir.blocks[0]
    assert title.block_type == BlockType.HEADING
    assert title.level == 1

    section = ir.blocks[2]
    assert section.block_type == BlockType.HEADING
    assert section.level == 2

    subsection = next(
        b for b in ir.blocks if b.block_type == BlockType.HEADING and b.text.startswith("3.2.1")
    )
    assert subsection.level == 3

    figures = [b for b in ir.blocks if b.block_type == BlockType.FIGURE]
    assert len(figures) == 1
    assert figures[0].figure is not None
    assert figures[0].figure.crop is None


def test_mapper_maps_formula_latex_into_text_slot() -> None:
    """A formula block carries its LaTeX in the text slot (chunking treats a formula as text)."""
    ir = MineruIRMapper.map_response(_CONTRACT, doc_id="d", source_hash="h")
    formula = next(b for b in ir.blocks if b.block_type == BlockType.FORMULA)
    assert formula.text.startswith("\\mathrm{Attention}")


# ==================== node — registration + brick shape ====================


def test_mineru_is_registered_under_the_parser_family() -> None:
    """The node self-registers as ('parser', 'mineru') and surfaces in the palette."""
    assert NodeRegistry.get("parser", "mineru") is ParserMineruNode
    assert "mineru" in NodeRegistry.kinds("parser")


def test_mineru_brick_shape_matches_the_plan() -> None:
    """An off-by-default escalation head: unique, PDF-only, scored, its own Config, no docling base."""
    assert ParserMineruNode.KIND == "mineru"
    assert ParserMineruNode.UNIQUE_IN_GRAPH is True
    assert ParserMineruNode.NATIVE_FORMATS == frozenset()
    assert ParserMineruNode.Config is ParserMineruConfig
    assert issubclass(ParserMineruNode, BaseParserNode)
    assert ParserMineruNode.describe().scored is True


# ==================== config ====================


def test_config_forbids_unknown_fields_and_defaults_base_url() -> None:
    """extra='forbid' (via NodeConfig) rejects a typo; base_url defaults to the in-stack sidecar."""
    with pytest.raises(ValidationError):
        ParserMineruConfig(base_url="http://x:80", do_ocr=True)
    assert ParserMineruConfig().base_url == "http://mineru_server:80"


def test_config_defaults_high_timeout_and_no_device_knob() -> None:
    """The VLM timeout defaults high; there is no device knob (deployment concern)."""
    cfg = ParserMineruConfig()
    assert cfg.timeout_seconds == 900.0
    assert "device" not in ParserMineruConfig.model_fields


def test_config_strips_whitespace_from_base_url() -> None:
    """A pasted trailing newline is stripped so the HTTP request line stays valid."""
    cfg = ParserMineruConfig(base_url="  http://mineru_server:80\n")
    assert cfg.base_url == "http://mineru_server:80"


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
    node = ParserMineruNode(
        id="p",
        config=ParserMineruConfig(base_url="http://mineru_server:80", api_key="tok"),
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
    assert len(out.ir.blocks) == 8
    assert out.score > 0.0


def test_parse_without_a_pdf_view_degrades_to_empty_ir() -> None:
    """No PDF view and no native path (NATIVE_FORMATS empty) → empty IR, score 0, no network call."""
    node = ParserMineruNode(id="p", config=ParserMineruConfig(base_url="http://mineru_server:80"))
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
    node = ParserMineruNode(id="p", config=ParserMineruConfig(base_url="http://mineru_server:80"))
    assert asyncio.run(node.preflight()) is None


def test_preflight_fails_on_rejected_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 401 on /health surfaces a rejected bearer token before any spend."""
    monkeypatch.setattr(httpx, "AsyncClient", _preflight_client(status_code=401))
    node = ParserMineruNode(
        id="p", config=ParserMineruConfig(base_url="http://mineru_server:80", api_key="bad")
    )
    with pytest.raises(PreflightError):
        asyncio.run(node.preflight())
