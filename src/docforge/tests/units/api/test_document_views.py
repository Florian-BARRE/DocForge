"""On-the-fly markdown/HTML document views (generated from the canonical IR, invariant #1).

Two concerns, all serviceless (the DB façade is mocked):
  1. IRBundleAdapter — the IRBundle(DB rows) -> DocumentIR reconstruction: enrichment fold onto the
     figure slot, BlockTable -> TableData, and reading_order preserved verbatim.
  2. The GET /documents/{id}/{markdown,html} endpoints — content-type, body and the ?download
     Content-Disposition contract.

`from backend...` and `from shared_libs...` imports are deferred behind the fastapi_app fixture so
module import never runs before the app puts app/ on sys.path and the shared_libs alias is live.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


# -------------------- fixtures & row builders --------------------
@pytest.fixture
def adapter(fastapi_app):
    """IRBundleAdapter, imported only after the app fixture put app/ on sys.path."""
    from backend.routers.explorer.ir_adapter import IRBundleAdapter  # noqa: PLC0415

    return IRBundleAdapter


@pytest.fixture
def ir_bundle(fastapi_app):
    """The IRBundle façade dataclass, imported after the shared_libs alias is live."""
    from shared_libs.services.db.facades import IRBundle  # noqa: PLC0415

    return IRBundle


@pytest.fixture
def enrich_enums(fastapi_app):
    """The enrichment kind/status enums used to build stand-in enrichment rows."""
    from shared_libs.services.db.postgresql.tables import (  # noqa: PLC0415
        EnrichmentKind,
        EnrichmentStatus,
    )

    return EnrichmentKind, EnrichmentStatus


def _block(
    *,
    block_id: str,
    block_type: str,
    reading_order: int,
    text: str | None = None,
    level: int | None = None,
) -> SimpleNamespace:
    """A minimal raw block row carrying only what the adapter reads."""
    return SimpleNamespace(
        id=block_id,
        block_type=block_type,
        page=0,
        bbox=[0.0, 0.0, 1.0, 1.0],
        reading_order=reading_order,
        parent_id=None,
        level=level,
        text=text,
        language=None,
    )


def _document() -> SimpleNamespace:
    """A minimal document row supplying the IR envelope + download filename."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        source_hash="deadbeef",
        title="My Report",
        page_count=3,
        language="en",
        filename="my-report.pdf",
    )


# -------------------- adapter: table mapping --------------------
def test_adapter_maps_table_row_to_table_data(adapter, ir_bundle) -> None:
    """A TABLE block's BlockTable row becomes canonical TableData on the block's table slot."""
    table_row = SimpleNamespace(
        block_id="b1",
        cells=[["h1", "h2"], ["a", "b"]],
        n_rows=2,
        n_cols=2,
        has_header=True,
        linearized_md="| h1 | h2 |",
    )
    bundle = ir_bundle(
        blocks=[_block(block_id="b1", block_type="table", reading_order=0)],
        tables=[table_row],
        figures=[],
        enrichments=[],
    )

    ir = adapter.to_document_ir(_document(), bundle)

    table = ir.blocks[0].table
    assert table is not None
    assert table.cells == [["h1", "h2"], ["a", "b"]]
    assert (table.n_rows, table.n_cols, table.has_header) == (2, 2, True)


# -------------------- adapter: enrichment fold --------------------
def test_adapter_folds_enrichments_onto_figure(adapter, ir_bundle, enrich_enums) -> None:
    """OCR/VLM/chart-to-data enrichments fold onto the figure slot; a FAILED row is ignored."""
    kind, status = enrich_enums
    figure_row = SimpleNamespace(block_id="f1", crop_blob_hash="abc", caption_block_id="c1")
    enrichments = [
        SimpleNamespace(
            block_id="f1", kind=kind.OCR, status=status.OK, text="ocr words", data=None
        ),
        SimpleNamespace(block_id="f1", kind=kind.VLM, status=status.OK, text="a chart", data=None),
        SimpleNamespace(
            block_id="f1",
            kind=kind.CHART_TO_DATA,
            status=status.OK,
            text=None,
            data=[["x", "y"], ["1", "2"]],
        ),
        # A failed VLM row must never overwrite the successful description.
        SimpleNamespace(block_id="f1", kind=kind.VLM, status=status.FAILED, text="junk", data=None),
    ]
    bundle = ir_bundle(
        blocks=[_block(block_id="f1", block_type="figure", reading_order=0)],
        tables=[],
        figures=[figure_row],
        enrichments=enrichments,
    )

    figure = adapter.to_document_ir(_document(), bundle).blocks[0].figure

    assert figure is not None
    assert figure.ocr_text == "ocr words"
    assert figure.description == "a chart"
    assert figure.data_table == [["x", "y"], ["1", "2"]]


def test_adapter_ignores_failed_only_enrichment(adapter, ir_bundle, enrich_enums) -> None:
    """A figure whose only OCR enrichment FAILED keeps an empty ocr_text slot."""
    kind, status = enrich_enums
    bundle = ir_bundle(
        blocks=[_block(block_id="f1", block_type="figure", reading_order=0)],
        tables=[],
        figures=[SimpleNamespace(block_id="f1", crop_blob_hash=None, caption_block_id=None)],
        enrichments=[
            SimpleNamespace(
                block_id="f1", kind=kind.OCR, status=status.FAILED, text="bad", data=None
            )
        ],
    )

    figure = adapter.to_document_ir(_document(), bundle).blocks[0].figure

    assert figure is not None
    assert figure.ocr_text is None


# -------------------- adapter: reading order --------------------
def test_adapter_preserves_reading_order(adapter, ir_bundle) -> None:
    """Reading order is carried verbatim onto every block (never dropped or resorted away)."""
    bundle = ir_bundle(
        blocks=[
            _block(block_id="h", block_type="heading", reading_order=5, text="Title", level=1),
            _block(block_id="fig", block_type="figure", reading_order=6),
            _block(block_id="cap", block_type="caption", reading_order=7, text="Figure 1."),
        ],
        tables=[],
        figures=[SimpleNamespace(block_id="fig", crop_blob_hash=None, caption_block_id="cap")],
        enrichments=[],
    )

    ir = adapter.to_document_ir(_document(), bundle)

    assert [block.reading_order for block in ir.blocks] == [5, 6, 7]
    # The envelope facts come from the document row, not the bundle.
    assert ir.title == "My Report"
    assert ir.n_pages == 3
    assert ir.language == "en"


def test_adapter_caption_folds_by_reading_order_adjacency(adapter, ir_bundle) -> None:
    """End-to-end: a CAPTION immediately after a FIGURE in reading order folds into the figure."""
    from shared_libs.pipelines.ingest.linearize import IRLinearizer  # noqa: PLC0415

    bundle = ir_bundle(
        blocks=[
            _block(block_id="fig", block_type="figure", reading_order=0),
            _block(block_id="cap", block_type="caption", reading_order=1, text="Figure 1: a plot."),
        ],
        tables=[],
        figures=[SimpleNamespace(block_id="fig", crop_blob_hash=None, caption_block_id="cap")],
        enrichments=[],
    )

    markdown = IRLinearizer().to_markdown(adapter.to_document_ir(_document(), bundle))

    assert "Figure 1: a plot." in markdown


# -------------------- endpoints --------------------
def _mock_database(monkeypatch, document, bundle) -> None:
    """Point CONTEXT.database at a stub whose documents façade returns the given doc + IR bundle."""
    from backend.context import CONTEXT  # noqa: PLC0415

    documents = SimpleNamespace(
        get=AsyncMock(return_value=document),
        get_ir=AsyncMock(return_value=bundle),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(documents=documents))


def test_markdown_endpoint_inline_content_type_and_body(
    client, fastapi_app, ir_bundle, monkeypatch
) -> None:
    """GET /documents/{id}/markdown returns a text/markdown body and no attachment by default."""
    document = _document()
    bundle = ir_bundle(
        blocks=[_block(block_id="h", block_type="heading", reading_order=0, text="Hello", level=1)],
        tables=[],
        figures=[],
        enrichments=[],
    )
    _mock_database(monkeypatch, document, bundle)

    response = client.get(f"/api/v1/documents/{document.id}/markdown")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.text == "# Hello"
    assert "content-disposition" not in response.headers


def test_html_endpoint_inline_content_type_and_body(
    client, fastapi_app, ir_bundle, monkeypatch
) -> None:
    """GET /documents/{id}/html returns a structural text/html body inline by default."""
    document = _document()
    bundle = ir_bundle(
        blocks=[_block(block_id="h", block_type="heading", reading_order=0, text="Hello", level=1)],
        tables=[],
        figures=[],
        enrichments=[],
    )
    _mock_database(monkeypatch, document, bundle)

    response = client.get(f"/api/v1/documents/{document.id}/html")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/html")
    assert "<h1>Hello</h1>" in response.text
    assert "content-disposition" not in response.headers


def test_markdown_download_sets_attachment_filename(
    client, fastapi_app, ir_bundle, monkeypatch
) -> None:
    """?download=1 attaches a Content-Disposition named after the source stem with the .md suffix."""
    document = _document()  # filename "my-report.pdf" -> stem "my-report"
    bundle = ir_bundle(
        blocks=[_block(block_id="h", block_type="heading", reading_order=0, text="Hi", level=1)],
        tables=[],
        figures=[],
        enrichments=[],
    )
    _mock_database(monkeypatch, document, bundle)

    response = client.get(f"/api/v1/documents/{document.id}/markdown?download=1")

    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"] == 'attachment; filename="my-report.md"'


def test_html_download_sets_attachment_filename(
    client, fastapi_app, ir_bundle, monkeypatch
) -> None:
    """?download=1 on the HTML view names the attachment <stem>.html."""
    document = _document()
    bundle = ir_bundle(
        blocks=[_block(block_id="h", block_type="heading", reading_order=0, text="Hi", level=1)],
        tables=[],
        figures=[],
        enrichments=[],
    )
    _mock_database(monkeypatch, document, bundle)

    response = client.get(f"/api/v1/documents/{document.id}/html?download=1")

    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"] == 'attachment; filename="my-report.html"'


def test_adapter_unknown_block_type_degrades_to_paragraph(adapter, ir_bundle) -> None:
    """An unknown stored block_type (forward-compat/legacy) renders as a paragraph, never crashes."""
    from shared_libs.public_models import BlockType  # noqa: PLC0415

    bundle = ir_bundle(
        blocks=[
            _block(block_id="x", block_type="hologram", reading_order=0, text="future block"),
        ],
        tables=[],
        figures=[],
        enrichments=[],
    )

    ir = adapter.to_document_ir(_document(), bundle)

    assert ir.blocks[0].block_type is BlockType.PARAGRAPH
    assert ir.blocks[0].text == "future block"


def test_unknown_block_type_does_not_500_the_view(
    client, fastapi_app, ir_bundle, monkeypatch
) -> None:
    """A document holding an unrecognized block_type still renders its markdown view (no 500)."""
    document = _document()
    bundle = ir_bundle(
        blocks=[_block(block_id="x", block_type="hologram", reading_order=0, text="future block")],
        tables=[],
        figures=[],
        enrichments=[],
    )
    _mock_database(monkeypatch, document, bundle)

    response = client.get(f"/api/v1/documents/{document.id}/markdown")

    assert response.status_code == 200, response.text
    assert "future block" in response.text


def _non_latin1_document(filename: str) -> SimpleNamespace:
    """A document row whose filename is not latin-1 encodable (accents / CJK)."""
    document = _document()
    document.filename = filename
    return document


@pytest.mark.parametrize(
    "filename, expected_ascii, expected_encoded",
    [
        ("rapport été 2026.pdf", "rapport t 2026.md", "rapport%20%C3%A9t%C3%A9%202026.md"),
        ("文档.pdf", "document.md", "%E6%96%87%E6%A1%A3.md"),
    ],
)
def test_download_non_latin1_filename_uses_rfc5987(
    client, fastapi_app, ir_bundle, monkeypatch, filename, expected_ascii, expected_encoded
) -> None:
    """A non-latin-1 filename downloads with an ASCII fallback + RFC 5987 filename*, no crash."""
    document = _non_latin1_document(filename)
    bundle = ir_bundle(
        blocks=[_block(block_id="h", block_type="heading", reading_order=0, text="Hi", level=1)],
        tables=[],
        figures=[],
        enrichments=[],
    )
    _mock_database(monkeypatch, document, bundle)

    response = client.get(f"/api/v1/documents/{document.id}/markdown?download=1")

    assert response.status_code == 200, response.text
    disposition = response.headers["content-disposition"]
    # The whole header must be latin-1 encodable (the crash the fix prevents).
    disposition.encode("latin-1")
    assert f'filename="{expected_ascii}"' in disposition
    assert f"filename*=UTF-8''{expected_encoded}" in disposition


def test_view_endpoints_unknown_document_is_404(client, fastapi_app, monkeypatch) -> None:
    """An unknown document id is a 404 on both view endpoints (guarded before rendering)."""
    from backend.context import CONTEXT  # noqa: PLC0415

    documents = SimpleNamespace(get=AsyncMock(return_value=None), get_ir=AsyncMock())
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(documents=documents))

    missing = uuid.uuid4()
    assert client.get(f"/api/v1/documents/{missing}/markdown").status_code == 404
    assert client.get(f"/api/v1/documents/{missing}/html").status_code == 404


def test_view_routes_are_registered(fastapi_app) -> None:
    """Both view endpoints appear in the OpenAPI contract as GET siblings of /ir."""
    paths = fastapi_app.openapi()["paths"]
    assert "get" in paths["/api/v1/documents/{document_id}/markdown"]
    assert "get" in paths["/api/v1/documents/{document_id}/html"]
