"""IRLinearizer: full-document markdown + HTML views over a canonical DocumentIR.

Asserts reading-order traversal, heading levels, list folding, table reuse (shared markdown grid),
figure caption/enrichment rendering, header/footer exclusion, and HTML escaping + semantic tags.
"""

from shared_libs.pipelines.ingest.linearize import (
    HtmlLinearizer,
    IRLinearizer,
    MarkdownLinearizer,
)
from shared_libs.public_models import (
    Block,
    BlockType,
    DocumentIR,
    FigureEnrichment,
    FigureKind,
    Provenance,
    TableData,
)


def _blk(
    bid, btype, order, text=None, level=None, table=None, figure=None, page=0
) -> Block:
    return Block(
        id=bid,
        block_type=btype,
        reading_order=order,
        level=level,
        provenance=Provenance(page=page, bbox=(0.1, 0.1, 0.9, 0.9)),
        text=text,
        table=table,
        figure=figure,
    )


def _sample_ir() -> DocumentIR:
    """A document exercising headings, prose, a list, a table, a captioned figure and boilerplate."""
    table = TableData(
        cells=[["City", "Pop"], ["Paris", "2M"], ["Lyon", "0.5M"]],
        n_rows=3,
        n_cols=2,
        has_header=True,
    )
    figure = FigureEnrichment(
        kind=FigureKind.CHART,
        description="A bar chart of revenue.",
        ocr_text="Q1 Q2 Q3",
        data_table=[["Quarter", "Revenue"], ["Q1", "10"], ["Q2", "20"]],
    )
    return DocumentIR(
        doc_id="doc1",
        source_hash="h",
        title="Report",
        n_pages=1,
        blocks=[
            # Deliberately out of reading order to prove the walker sorts.
            _blk("p1", BlockType.PARAGRAPH, 2, text="First paragraph."),
            _blk("h1", BlockType.HEADING, 1, text="Overview", level=1),
            _blk("hf", BlockType.HEADER_FOOTER, 0, text="Confidential footer"),
            _blk("h2", BlockType.HEADING, 3, text="Details", level=2),
            _blk("li1", BlockType.LIST_ITEM, 4, text="Alpha"),
            _blk("li2", BlockType.LIST_ITEM, 5, text="Beta"),
            _blk("t1", BlockType.TABLE, 6, table=table),
            _blk("f1", BlockType.FIGURE, 7, figure=figure),
            _blk("cap", BlockType.CAPTION, 8, text="Figure 1: revenue"),
        ],
    )


# -------------------- markdown --------------------
def test_linearize_markdown_structure_and_order() -> None:
    md = MarkdownLinearizer().render(_sample_ir())
    # Boilerplate header/footer excluded from the view.
    assert "Confidential footer" not in md
    # Heading levels and reading order (H1 before its paragraph, H2 later).
    assert md.index("# Overview") < md.index("First paragraph.") < md.index("## Details")
    # List items folded into one dash list.
    assert "- Alpha\n- Beta" in md
    # Table rendered through the shared markdown grid (header separator present).
    assert "| City | Pop |" in md
    assert "| --- | --- |" in md
    assert "| Paris | 2M |" in md


def test_linearize_markdown_figure_caption_and_enrichment() -> None:
    md = MarkdownLinearizer().render(_sample_ir())
    # Adjacent caption is folded into the figure (italic), not emitted as a separate block.
    assert "*Figure 1: revenue*" in md
    # VLM description and OCR text both surface.
    assert "A bar chart of revenue." in md
    assert "Q1 Q2 Q3" in md
    # Chart-to-data grid rendered via the same shared table renderer.
    assert "| Quarter | Revenue |" in md


def test_linearize_markdown_empty_figure_renders_nothing() -> None:
    ir = DocumentIR(
        doc_id="d",
        source_hash="h",
        blocks=[_blk("f", BlockType.FIGURE, 0, figure=FigureEnrichment(kind=FigureKind.PHOTO))],
    )
    assert MarkdownLinearizer().render(ir) == ""


# -------------------- html --------------------
def test_linearize_html_semantic_tags() -> None:
    html = HtmlLinearizer().render(_sample_ir())
    assert "<h1>Overview</h1>" in html
    assert "<h2>Details</h2>" in html
    assert "<p>First paragraph.</p>" in html
    assert "<ul><li>Alpha</li><li>Beta</li></ul>" in html
    # Table: thead of <th> for the header row, tbody of <td> for the rest.
    assert "<thead><tr><th>City</th><th>Pop</th></tr></thead>" in html
    assert "<tbody><tr><td>Paris</td><td>2M</td></tr>" in html
    # Figure with a figcaption folded from the adjacent caption block.
    assert "<figure>" in html and "<figcaption>Figure 1: revenue</figcaption></figure>" in html


def test_linearize_html_escapes_text() -> None:
    ir = DocumentIR(
        doc_id="d",
        source_hash="h",
        blocks=[
            _blk("h", BlockType.HEADING, 0, text="A & B <tag>", level=1),
            _blk("p", BlockType.PARAGRAPH, 1, text='"quote" <script>alert(1)</script>'),
            _blk(
                "t",
                BlockType.TABLE,
                2,
                table=TableData(cells=[["<b>x</b>"]], n_rows=1, n_cols=1, has_header=False),
            ),
        ],
    )
    html = HtmlLinearizer().render(ir)
    assert "<h1>A &amp; B &lt;tag&gt;</h1>" in html
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<td>&lt;b&gt;x&lt;/b&gt;</td>" in html


# -------------------- facade --------------------
def test_ir_linearizer_facade_delegates() -> None:
    linearizer = IRLinearizer()
    ir = _sample_ir()
    assert linearizer.to_markdown(ir) == MarkdownLinearizer().render(ir)
    assert linearizer.to_html(ir) == HtmlLinearizer().render(ir)
