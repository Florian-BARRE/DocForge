"""Explorer read surface (wave A): the display title follows the collection's ``title_field``
(read-time, the raw parsed ``title`` stays alongside), and every 0-based page carries its 1-based
reader page next to it — ``page_number`` on chunks and IR blocks, ``page_label`` on pages (whose
``page_number`` already meant the 0-based index and is left unchanged)."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shared_libs.services.db.postgresql.tables import DocumentStatus, SourceKind

DOC_ID = uuid.uuid4()
COLLECTION_ID = uuid.uuid4()


@pytest.fixture
def helpers(fastapi_app):
    from backend.routers.explorer.helpers import ExplorerHelpers  # noqa: PLC0415

    return ExplorerHelpers


def _document(title: str = "1 GÉNÉRALITÉS") -> SimpleNamespace:
    return SimpleNamespace(
        id=DOC_ID,
        collection_id=COLLECTION_ID,
        filename="p.pdf",
        format="pdf",
        mime_type="application/pdf",
        file_size=10,
        page_count=3,
        language="fr",
        title=title,
        source_kind=SourceKind.DIGITAL_BORN,
        status=DocumentStatus.DONE,
        source_hash="h",
        pdf_blob_hash=None,
        simhash=None,
        pipeline_version="v",
        created_at=None,
        enabled=True,
        chunk_count=2,
        warning_reason=None,
    )


def _meta(field_id: int, value) -> SimpleNamespace:
    return SimpleNamespace(field_id=field_id, value=value, origin="user")


NAMES = {1: "topic", 2: "keywords"}


@pytest.mark.parametrize(
    ("title_field", "rows", "expected"),
    [
        (None, [_meta(1, "Achats")], "1 GÉNÉRALITÉS"),
        ("topic", [_meta(1, "Achats")], "Achats"),
        ("topic", [_meta(1, "  ")], "1 GÉNÉRALITÉS"),  # blank value → parsed title
        ("topic", [], "1 GÉNÉRALITÉS"),  # unset on this document → parsed title
        ("keywords", [_meta(2, ["a", "b"])], "a, b"),
    ],
)
def test_display_title_resolution(helpers, title_field, rows, expected) -> None:
    assert helpers.display_title(_document(), rows, NAMES, title_field) == expected


def test_list_item_and_detail_keep_raw_title_and_add_display_title(helpers) -> None:
    item = helpers.list_item(_document(), "Achats")
    assert (item.title, item.display_title) == ("1 GÉNÉRALITÉS", "Achats")
    assert helpers.list_item(_document()).display_title == "1 GÉNÉRALITÉS"
    detail = helpers.detail(_document(), [], display_title="Achats")
    assert (detail.title, detail.display_title) == ("1 GÉNÉRALITÉS", "Achats")


def test_grid_row_resolves_display_title(fastapi_app) -> None:
    from backend.libs.corpus.mapper import CorpusMapper  # noqa: PLC0415

    row = CorpusMapper.grid_row(_document(), [_meta(1, "Achats")], NAMES, "topic")
    assert (row.title, row.display_title) == ("1 GÉNÉRALITÉS", "Achats")
    assert CorpusMapper.grid_row(_document(), [], NAMES).display_title == "1 GÉNÉRALITÉS"


def test_document_detail_route_returns_display_title(client, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415

    collections = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(id=COLLECTION_ID, title_field="topic")),
        get_schema=AsyncMock(return_value=[SimpleNamespace(id=1, field_name="topic")]),
    )
    documents = SimpleNamespace(
        get=AsyncMock(return_value=_document()),
        get_metadata=AsyncMock(return_value=[_meta(1, "Achats")]),
    )
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(collections=collections, documents=documents)
    )
    response = client.get(f"/api/v1/documents/{DOC_ID}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["title"], body["display_title"]) == ("1 GÉNÉRALITÉS", "Achats")


# ─────────────────────────── 1-based pages ───────────────────────────


def test_page_keeps_zero_based_page_number_and_adds_page_label(helpers) -> None:
    page = SimpleNamespace(
        page_number=0, width=1.0, height=1.0, is_scanned=False, language=None, render_blob_hash=None
    )
    info = helpers.page(page)
    assert (info.page_number, info.page_label) == (0, 1)


@pytest.mark.parametrize(("page", "expected"), [(4, 5), (None, None)])
def test_chunk_carries_one_based_page_number(helpers, page, expected) -> None:
    chunk = SimpleNamespace(
        id=uuid.uuid4(),
        chunk_index=0,
        text="t",
        token_count=1,
        is_indexed=True,
        strategy="recursive",
        parent_id=None,
        role="body",
        enabled_override=None,
        heading_path=None,
    )
    info = helpers.chunk(chunk, [], [], page=page)
    assert (info.page, info.page_number) == (page, expected)


def test_ir_block_carries_one_based_page_number(helpers) -> None:
    block = SimpleNamespace(
        id="b1",
        block_type="paragraph",
        page=2,
        bbox=(0.0, 0.0, 1.0, 1.0),
        reading_order=0,
        parent_id=None,
        level=None,
        text="t",
        is_boilerplate=False,
        language=None,
    )
    bundle = SimpleNamespace(blocks=[block], tables=[], figures=[], enrichments=[])
    ir_block = helpers.ir(bundle).blocks[0]
    assert (ir_block.page, ir_block.page_number) == (2, 3)
