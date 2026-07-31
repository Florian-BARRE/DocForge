"""The native (page-less) parse path — html/md reach Docling as ORIGINAL bytes.

Two guarantees are locked here without needing Docling installed:
  1. DoclingIRMapper keeps the full heading tree of a page-less document (num_pages == 0, items
     with no bbox) instead of dropping every block for lack of provenance — the regression that
     collapsed a structured HTML charter into a single chunk.
  2. BaseParserNode routes a NATIVE_FORMATS source (no PDF view) to the engine instead of degrading
     it to an empty IR, and still degrades a non-native source that has no PDF view.
"""

import asyncio
from types import SimpleNamespace

from shared_libs.pipelines.base import NodeConfig
from shared_libs.pipelines.ingest.nodes.parse.parser.base import BaseParserNode
from shared_libs.pipelines.ingest.nodes.parse.parser.docling.mapper import DoclingIRMapper
from shared_libs.public_models import BlockType, DocumentIR, IntakeResult


def _item(label: str, text: str, ref: str, level: int | None = None) -> SimpleNamespace:
    """A minimal stand-in for a page-less Docling item: a label, text via .text, NO provenance.

    Mirrors what Docling emits for native html/md — get_text() returns None while .text carries the
    content, and prov is empty (there are no pages/bboxes).
    """
    return SimpleNamespace(
        label=SimpleNamespace(value=label),
        text=text,
        prov=[],
        self_ref=ref,
        level=level,
        get_text=lambda: None,
    )


def _pageless_doc(items: list[SimpleNamespace]) -> SimpleNamespace:
    """A page-less Docling document (num_pages() == 0) yielding the given items in order."""
    return SimpleNamespace(
        num_pages=lambda: 0,
        pages={},
        language="en",
        iterate_items=lambda: ((it, 0) for it in items),
    )


def test_mapper_keeps_the_heading_tree_of_a_pageless_html_document() -> None:
    """A title + articles (h2) + clauses map to heading/paragraph blocks with synthetic provenance."""
    items = [
        _item("title", "Data Protection Charter", "#/texts/0"),
        _item("section_header", "Article 1 - Data retention", "#/texts/1", level=1),
        _item("text", "Personal data shall be retained for 12 months.", "#/texts/2"),
        _item("section_header", "Article 2 - Breach notification", "#/texts/3", level=1),
        _item("text", "A breach shall be reported within 24 hours.", "#/texts/4"),
    ]
    ir = DoclingIRMapper.map_document(_pageless_doc(items), doc_id="d", source_hash="h")

    # 1. Every item survives (none dropped for missing provenance) with its text intact.
    assert len(ir.blocks) == 5
    headings = [b for b in ir.blocks if b.block_type == BlockType.HEADING]
    assert [b.text for b in headings] == [
        "Data Protection Charter",
        "Article 1 - Data retention",
        "Article 2 - Breach notification",
    ]
    # 2. Page-less items get the synthetic full-page provenance instead of being discarded.
    assert all(b.provenance.page == 0 for b in ir.blocks)
    assert all(b.provenance.bbox == (0.0, 0.0, 1.0, 1.0) for b in ir.blocks)
    # 3. The heading tree links each clause under its own article (per-article boundaries survive).
    article_2 = headings[2]
    clause_2 = ir.blocks[4]
    assert clause_2.block_type == BlockType.PARAGRAPH
    assert clause_2.parent_id == article_2.id


def test_mapper_preserves_html_heading_levels_so_articles_nest_under_the_title() -> None:
    """Docling gives the title (h1) no level and numbers section headers (h2, h3, …) from 1, which
    naively flattens the h1 title and the h2 articles to the same level. The mapper must recover the
    real HTML levels — h1 → 1, h2 → 2 — so every article nests UNDER the charter title, not under
    the first article."""
    items = [
        _item("title", "Data Protection Charter", "#/texts/0"),  # <h1>, no docling level
        _item("section_header", "Article 1", "#/texts/1", level=1),  # <h2>, docling level 1
        _item("text", "Clause one.", "#/texts/2"),
        _item("section_header", "Article 2", "#/texts/3", level=1),  # <h2>, docling level 1
        _item("text", "Clause two.", "#/texts/4"),
    ]
    ir = DoclingIRMapper.map_document(_pageless_doc(items), doc_id="d", source_hash="h")

    headings = [b for b in ir.blocks if b.block_type == BlockType.HEADING]
    # 1. The title stays level 1; both h2 articles become level 2 (not flattened to 1).
    assert [b.level for b in headings] == [1, 2, 2]
    # 2. Each article nests under the title — the breadcrumb reads Title › Article, never
    #    Article 1 › Article 2.
    title, article_1, article_2 = headings
    assert article_1.parent_id == title.id
    assert article_2.parent_id == title.id


class _FakeParser(BaseParserNode):
    """A concrete parser that parses one native format and records which bytes it received."""

    KIND = "fake"
    NAME = "Fake"
    SUMMARY = "test parser"
    Config = NodeConfig
    NATIVE_FORMATS = frozenset({"html"})

    def __init__(self, id: str, config: NodeConfig) -> None:
        super().__init__(id=id, config=config)
        self.parsed: IntakeResult | None = None

    async def _parse(self, source: IntakeResult) -> DocumentIR:
        self.parsed = source
        return DocumentIR(doc_id=source.source_hash, source_hash=source.source_hash)


def _run(source: IntakeResult):
    node = _FakeParser(id="p", config=NodeConfig())
    out = asyncio.run(node.run(BaseParserNode.Consumes(source=source)))
    return node, out


def test_native_source_without_pdf_view_reaches_the_engine() -> None:
    """An html source (no PDF view) is parsed natively from its original bytes, not degraded."""
    node, out = _run(
        IntakeResult(source_hash="h", source_format="html", source_content=b"<h1>x</h1>")
    )
    assert node.parsed is not None  # the engine was invoked
    assert node.parsed.source_content == b"<h1>x</h1>"


def test_non_native_source_without_pdf_view_degrades_to_empty_ir() -> None:
    """A format with neither a PDF view nor native support degrades to an empty IR (score 0)."""
    node, out = _run(IntakeResult(source_hash="h", source_format="docx", source_content=b"raw"))
    assert node.parsed is None  # the engine was NOT invoked
    assert out.ir.blocks == []
    assert out.score == 0.0
