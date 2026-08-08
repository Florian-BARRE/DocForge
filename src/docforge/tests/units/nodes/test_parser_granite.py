"""The Granite-Docling VLM parser brick — registration, config shape, VLM converter build, and the
proof that it reuses the UNCHANGED DoclingIRMapper.

Everything is mocked (no real docling / no 515 MB model), mirroring how the standard docling node is
tested: fake `docling.*` modules are injected only for the `_build_converter` call so the assertions
stay fully offline.
"""

import asyncio
import sys
from types import ModuleType, SimpleNamespace

import pytest
from pydantic import ValidationError

from shared_libs.pipelines.ingest.nodes.parse.parser.base import BaseParserNode
from shared_libs.pipelines.ingest.nodes.parse.parser.docling.mapper import DoclingIRMapper
from shared_libs.pipelines.ingest.nodes.parse.parser.docling_base import BaseDoclingParserNode
from shared_libs.pipelines.ingest.nodes.parse.parser.granite_docling.config import (
    ParserGraniteDoclingConfig,
)
from shared_libs.pipelines.ingest.nodes.parse.parser.granite_docling.core import (
    ParserGraniteDoclingNode,
)
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import BlockType, DocumentIR, IntakeResult

_PINNED_REVISION = "982fe3b40f2fa73c365bdb1bcacf6c81b7184bfe"


# ==================== registration + brick shape ====================


def test_granite_is_registered_under_the_parser_family() -> None:
    """The node self-registers as ('parser', 'granite_docling') and surfaces in the palette."""
    node_cls = NodeRegistry.get("parser", "granite_docling")
    assert node_cls is ParserGraniteDoclingNode
    assert "granite_docling" in NodeRegistry.kinds("parser")


def test_granite_brick_shape_matches_the_plan() -> None:
    """A GPU escalation head: unique, PDF-only (no native path), scored, its own Config."""
    assert ParserGraniteDoclingNode.KIND == "granite_docling"
    assert ParserGraniteDoclingNode.UNIQUE_IN_GRAPH is True
    assert ParserGraniteDoclingNode.NATIVE_FORMATS == frozenset()
    assert ParserGraniteDoclingNode.Config is ParserGraniteDoclingConfig
    assert issubclass(ParserGraniteDoclingNode, BaseDoclingParserNode)
    assert ParserGraniteDoclingNode.describe().scored is True


def test_granite_and_docling_never_share_a_converter_cache() -> None:
    """Per-concrete-class caches + a pipeline-discriminated key keep the two flavours isolated."""
    docling_cls = NodeRegistry.get("parser", "docling")
    assert docling_cls._converters is not ParserGraniteDoclingNode._converters
    assert docling_cls._build_lock is not ParserGraniteDoclingNode._build_lock
    assert ParserGraniteDoclingNode._PIPELINE == "vlm"


# ==================== config ====================


def test_config_pins_the_model_revision_by_default() -> None:
    """The default revision is the pinned commit so runtime HF fetches are reproducible."""
    cfg = ParserGraniteDoclingConfig()
    assert cfg.revision == _PINNED_REVISION
    assert cfg.force_backend_text is False
    assert cfg.max_new_tokens == 4096


def test_config_forbids_unknown_fields() -> None:
    """extra='forbid' (via NodeConfig): a typo in a stored blob fails the build, never ignored."""
    with pytest.raises(ValidationError):
        ParserGraniteDoclingConfig(do_ocr=True)


# ==================== _parse degradation (inherited from the base) ====================


def test_parse_degrades_to_empty_ir_without_a_pdf_view() -> None:
    """No PDF view and no native path (NATIVE_FORMATS is empty) → empty IR, score 0."""
    node = ParserGraniteDoclingNode(id="p", config=ParserGraniteDoclingConfig())
    source = IntakeResult(source_hash="h", source_format="html", source_content=b"<h1>x</h1>")
    out = asyncio.run(node.run(BaseParserNode.Consumes(source=source)))
    assert out.ir.blocks == []
    assert out.score == 0.0


# ==================== _build_converter — the exact VLM call ====================


class _FakeSpec(SimpleNamespace):
    """Stand-in for InlineVlmOptions: records the model_copy(update=...) payload."""

    def model_copy(self, update: dict) -> "_FakeSpec":
        return _FakeSpec(repo_id=self.repo_id, **update)


def _install_fake_docling(monkeypatch: pytest.MonkeyPatch, captured: dict) -> None:
    """Inject fake docling.* modules so _build_converter's lazy imports resolve and are captured."""

    def _module(name: str, **attrs: object) -> ModuleType:
        mod = ModuleType(name)
        for key, value in attrs.items():
            setattr(mod, key, value)
        monkeypatch.setitem(sys.modules, name, mod)
        return mod

    class _DocumentConverter:
        def __init__(self, format_options: dict) -> None:
            captured["format_options"] = format_options

    class _PdfFormatOption(SimpleNamespace):
        pass

    class _VlmPipelineOptions(SimpleNamespace):
        pass

    spec = _FakeSpec(repo_id="ibm-granite/granite-docling-258M")
    _module("docling", datamodel=None, document_converter=None, pipeline=None)
    _module("docling.datamodel")
    _module("docling.datamodel.vlm_model_specs", GRANITEDOCLING_TRANSFORMERS=spec)
    _module("docling.datamodel.base_models", InputFormat=SimpleNamespace(PDF="pdf"))
    _module("docling.datamodel.pipeline_options", VlmPipelineOptions=_VlmPipelineOptions)
    _module(
        "docling.document_converter",
        DocumentConverter=_DocumentConverter,
        PdfFormatOption=_PdfFormatOption,
    )
    _module("docling.pipeline")
    _module("docling.pipeline.vlm_pipeline", VlmPipeline="VlmPipelineClass")


def test_build_converter_swaps_in_vlm_pipeline_with_the_pinned_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The converter builds the VLM pipeline on the granite spec, revision- and token-pinned."""
    captured: dict = {}
    _install_fake_docling(monkeypatch, captured)

    node = ParserGraniteDoclingNode(
        id="p", config=ParserGraniteDoclingConfig(revision="deadbeef", max_new_tokens=2048)
    )
    node._build_converter()

    pdf_option = captured["format_options"]["pdf"]
    # 1. The WHOLE pipeline is swapped to VlmPipeline (not just its options).
    assert pdf_option.pipeline_cls == "VlmPipelineClass"
    # 2. It runs on the granite-docling spec, revision + token budget applied via model_copy.
    vlm_options = pdf_option.pipeline_options.vlm_options
    assert vlm_options.repo_id == "ibm-granite/granite-docling-258M"
    assert vlm_options.revision == "deadbeef"
    assert vlm_options.max_new_tokens == 2048
    # 3. force_backend_text is threaded onto the VLM pipeline options.
    assert pdf_option.pipeline_options.force_backend_text is False


# ==================== mapper reuse — the "unchanged mapper" guarantee ====================


def _item(label: str, text: str, ref: str, level: int | None = None) -> SimpleNamespace:
    """A minimal page-less Docling item (label + text, no provenance) — as DocTags-loaded items."""
    return SimpleNamespace(
        label=SimpleNamespace(value=label),
        text=text,
        prov=[],
        self_ref=ref,
        level=level,
        get_text=lambda: None,
    )


def test_granite_output_flows_through_the_unchanged_docling_mapper() -> None:
    """A granite-style DoclingDocument maps to a well-formed IR via the SAME mapper as docling."""
    items = [
        _item("title", "Quarterly Report", "#/texts/0"),
        _item("section_header", "Revenue", "#/texts/1", level=1),
        _item("text", "Revenue grew 12% year over year.", "#/texts/2"),
    ]
    doc = SimpleNamespace(
        num_pages=lambda: 0,
        pages={},
        language="en",
        iterate_items=lambda: ((it, 0) for it in items),
    )
    ir: DocumentIR = DoclingIRMapper.map_document(doc, doc_id="d", source_hash="h")

    assert len(ir.blocks) == 3
    headings = [b.text for b in ir.blocks if b.block_type == BlockType.HEADING]
    assert headings == ["Quarterly Report", "Revenue"]
    assert ir.blocks[2].block_type == BlockType.PARAGRAPH
