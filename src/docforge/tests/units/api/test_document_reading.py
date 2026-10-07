"""Reading a document piecemeal (agent-UX wave D): page-range views, outline, chunk context and the
paginated / lean chunk listing.

All store access is mocked (CONTEXT.database / CONTEXT.document_reader). ``from backend...`` and
``from shared_libs...`` imports are deferred behind the ``fastapi_app`` fixture (module-top imports
would run before app/ is on sys.path).
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

COLL_A = "11111111-1111-1111-1111-111111111111"
COLL_B = "22222222-2222-2222-2222-222222222222"


# ── fakes ────────────────────────────────────────────────────────────────────────────────────────
def _principal(collection_id: str):
    """A scoped key granting read on exactly one collection."""
    from backend.libs.auth.principal import AuthPrincipal  # noqa: PLC0415

    key = SimpleNamespace(
        permissions={"capabilities": ["read"], "collections": [collection_id]},
        revoked_at=None,
        user_id="u",
    )
    return AuthPrincipal(user=SimpleNamespace(is_active=True), key=key, is_full_access=False)


def _document(page_count: int | None = 3, collection_id: str = COLL_A) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        collection_id=uuid.UUID(collection_id),
        source_hash="deadbeef",
        title="Report",
        page_count=page_count,
        language="en",
        filename="report.pdf",
    )


def _block(block_id: str, page: int, order: int, text: str, block_type: str = "paragraph"):
    return SimpleNamespace(
        id=block_id,
        block_type=block_type,
        page=page,
        bbox=[0.0, 0.0, 1.0, 1.0],
        reading_order=order,
        parent_id=None,
        level=1 if block_type == "heading" else None,
        text=text,
        language=None,
    )


def _bundle(blocks):
    from shared_libs.services.db.facades import IRBundle  # noqa: PLC0415

    return IRBundle(blocks=blocks, tables=[], figures=[], enrichments=[])


def _mock_views(monkeypatch, document, bundle) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415

    documents = SimpleNamespace(
        get=AsyncMock(return_value=document), get_ir=AsyncMock(return_value=bundle)
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(documents=documents))


def _three_page_bundle():
    return _bundle(
        [
            _block("h", 0, 0, "Intro", "heading"),
            _block("p0", 0, 1, "page one text"),
            _block("p1", 1, 2, "page two text"),
            _block("p2", 2, 3, "page three <b>text</b>"),
        ]
    )


# ── D-1: page selector parsing ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("2", [2]),
        ("1-3", [1, 2, 3]),
        ("3,1-2", [1, 2, 3]),
        (" 2 , 2-3 ", [2, 3]),
        ("5,7-9", [5, 7, 8, 9]),
    ],
)
def test_page_range_parses_singles_ranges_and_lists(fastapi_app, spec, expected) -> None:
    from backend.libs.reading import PageRangeParser  # noqa: PLC0415

    assert PageRangeParser.parse(spec, 10) == expected


@pytest.mark.parametrize("spec", ["", "a", "1-", "-2", "1--2", "0", "3-1", "1;2", "1,,2"])
def test_page_range_rejects_bad_syntax_naming_page_count(fastapi_app, spec) -> None:
    from backend.libs.reading import PageRangeError, PageRangeParser  # noqa: PLC0415

    with pytest.raises(PageRangeError) as exc:
        PageRangeParser.parse(spec, 6)
    assert "6 pages" in str(exc.value)


def test_page_range_out_of_range_and_huge_range_rejected_without_expansion(fastapi_app) -> None:
    from backend.libs.reading import PageRangeError, PageRangeParser  # noqa: PLC0415

    with pytest.raises(PageRangeError, match="Page 7 is out of range — this document has 6 pages"):
        PageRangeParser.parse("2,7", 6)
    with pytest.raises(PageRangeError):
        PageRangeParser.parse("1-999999999999", 6)


def test_page_range_on_pageless_document_is_rejected(fastapi_app) -> None:
    from backend.libs.reading import PageRangeError, PageRangeParser  # noqa: PLC0415

    with pytest.raises(PageRangeError, match="no pages"):
        PageRangeParser.parse("1", 0)


# ── D-1: page-filtered views ─────────────────────────────────────────────────────────────────────
def test_markdown_pages_renders_only_selected_pages_with_markers(
    client, fastapi_app, monkeypatch
) -> None:
    document = _document()
    _mock_views(monkeypatch, document, _three_page_bundle())

    response = client.get(f"/api/v1/documents/{document.id}/markdown?pages=1,3")

    assert response.status_code == 200
    body = response.text
    assert body.startswith("<!-- page 1 -->\n\n# Intro")
    assert "<!-- page 3 -->\n\npage three <b>text</b>" in body
    assert "page two text" not in body and "<!-- page 2 -->" not in body


def test_markdown_without_pages_is_unchanged(client, fastapi_app, monkeypatch) -> None:
    document = _document()
    _mock_views(monkeypatch, document, _three_page_bundle())

    body = client.get(f"/api/v1/documents/{document.id}/markdown").text

    assert "<!-- page" not in body
    assert body == "# Intro\n\npage one text\n\npage two text\n\npage three <b>text</b>"


def test_html_pages_is_one_full_utf8_document_with_page_sections(
    client, fastapi_app, monkeypatch
) -> None:
    document = _document()
    _mock_views(monkeypatch, document, _three_page_bundle())

    response = client.get(f"/api/v1/documents/{document.id}/html?pages=2-3")

    assert response.status_code == 200
    body = response.text
    assert body.startswith("<!DOCTYPE html>") and body.count("<html") == 1
    assert '<meta charset="utf-8">' in body and body.rstrip().endswith("</html>")
    assert '<section data-page="2">\n<p>page two text</p>\n</section>' in body
    assert '<section data-page="3">' in body and "&lt;b&gt;" in body
    assert "page one text" not in body and 'data-page="1"' not in body


def test_view_pages_empty_page_keeps_its_marker(client, fastapi_app, monkeypatch) -> None:
    document = _document(page_count=4)
    _mock_views(monkeypatch, document, _three_page_bundle())

    body = client.get(f"/api/v1/documents/{document.id}/markdown?pages=4").text

    assert body == "<!-- page 4 -->"


@pytest.mark.parametrize("view", ["markdown", "html"])
@pytest.mark.parametrize("pages", ["9", "x", "2-1"])
def test_view_bad_pages_is_422_naming_page_count(
    client, fastapi_app, monkeypatch, view, pages
) -> None:
    document = _document()
    _mock_views(monkeypatch, document, _three_page_bundle())

    response = client.get(f"/api/v1/documents/{document.id}/{view}?pages={pages}")

    assert response.status_code == 422
    assert "3 pages" in response.json()["detail"]


async def test_view_pages_scoped_key_foreign_is_403(fastapi_app, monkeypatch) -> None:
    from backend.routers.explorer.router import get_document_markdown  # noqa: PLC0415

    _mock_views(monkeypatch, _document(collection_id=COLL_B), _three_page_bundle())
    with pytest.raises(HTTPException) as exc:
        await get_document_markdown(
            document_id=uuid.uuid4(), download=False, pages="1", principal=_principal(COLL_A)
        )
    assert exc.value.status_code == 403


# ── D-2: outline ─────────────────────────────────────────────────────────────────────────────────
def _heading(text, level, page, order):
    from shared_libs.services.db.facades import HeadingEntry  # noqa: PLC0415

    return HeadingEntry(text=text, level=level, page=page, reading_order=order)


def _entry(index, path, role="body", override=None, last_order=None):
    from shared_libs.services.db.facades import ChunkIndexEntry  # noqa: PLC0415

    return ChunkIndexEntry(
        id=uuid.UUID(int=index + 1),
        chunk_index=index,
        role=role,
        enabled_override=override,
        heading_path=path,
        last_reading_order=last_order,
    )


def test_outline_levels_pages_and_chunk_links(fastapi_app) -> None:
    from backend.libs.reading import OutlineBuilder  # noqa: PLC0415

    headings = [
        _heading("Part A", 1, 0, 0),
        _heading("Introduction", 2, 0, 1),
        _heading("  ", 2, 0, 2),
        _heading("Part B", 1, 2, 4),
        _heading("Introduction", 2, 2, 5),
        _heading("Orphan", 3, None, 9),
    ]
    chunks = [
        _entry(0, ["Part A"], last_order=0),
        _entry(1, ["Part A", "Introduction"], last_order=3),
        _entry(2, ["Part B", "Introduction"], last_order=6),
    ]

    outline = OutlineBuilder.build(headings, chunks)

    assert [(h.level, h.text, h.page_number) for h in outline] == [
        (1, "Part A", 1),
        (2, "Introduction", 1),
        (1, "Part B", 3),
        (2, "Introduction", 3),
        (3, "Orphan", None),
    ]
    # Each heading links to the first chunk ending at/after it; past the last chunk links nothing.
    assert [h.chunk_id for h in outline] == [
        str(uuid.UUID(int=1)),
        str(uuid.UUID(int=2)),
        str(uuid.UUID(int=3)),
        str(uuid.UUID(int=3)),
        None,
    ]


def test_outline_links_repeated_titles_by_position_not_text(fastapi_app) -> None:
    """Ratchet for the text-matching mis-link: a title repeated under two chapters, and a chunk
    breadcrumb that skips a level, must still link every heading to its own section."""
    from backend.libs.reading import OutlineBuilder  # noqa: PLC0415

    headings = [
        _heading("Chapter 1", 1, 0, 0),
        _heading("Results", 2, 0, 2),
        _heading("Discussion", 2, 1, 4),
        _heading("Chapter 2", 1, 2, 6),
        _heading("Results", 2, 2, 7),
    ]
    # c0 covers chapter 1 entirely (its breadcrumb never names Results/Discussion); c1 is chapter 2.
    chunks = [
        _entry(0, ["Chapter 1"], last_order=5),
        _entry(1, ["Chapter 2", "Results"], last_order=8),
    ]

    linked = [(h.text, h.chunk_id) for h in OutlineBuilder.build(headings, chunks)]

    first, second = str(uuid.UUID(int=1)), str(uuid.UUID(int=2))
    assert linked == [
        ("Chapter 1", first),
        ("Results", first),
        ("Discussion", first),
        ("Chapter 2", second),
        ("Results", second),
    ]


def test_outline_skips_block_less_chunks(fastapi_app) -> None:
    from backend.libs.reading import OutlineBuilder  # noqa: PLC0415

    headings = [_heading("Only", 1, 0, 1)]
    chunks = [_entry(0, ["Only"]), _entry(1, ["Only"], last_order=2)]

    assert [h.chunk_id for h in OutlineBuilder.build(headings, chunks)] == [str(uuid.UUID(int=2))]


def _mock_reader(monkeypatch, documents, collections=None):
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.libs.reading import DocumentReader  # noqa: PLC0415

    collections = collections or SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(title_field=None)),
        get_schema=AsyncMock(return_value=[]),
    )
    database = SimpleNamespace(documents=documents, collections=collections)
    monkeypatch.setattr(CONTEXT, "document_reader", DocumentReader(database), raising=False)


def test_outline_route_returns_envelope(client, fastapi_app, monkeypatch) -> None:
    document = _document(page_count=6)
    documents = SimpleNamespace(
        get=AsyncMock(return_value=document),
        get_headings=AsyncMock(return_value=[_heading("Scope", 1, 1, 0)]),
        get_chunk_index=AsyncMock(return_value=[_entry(0, ["Scope"], last_order=0)]),
    )
    _mock_reader(monkeypatch, documents)

    response = client.get(f"/api/v1/documents/{document.id}/outline")

    assert response.status_code == 200
    assert response.json() == {
        "document_id": str(document.id),
        "display_title": "Report",
        "page_count": 6,
        "headings": [
            {"level": 1, "text": "Scope", "page_number": 2, "chunk_id": str(uuid.UUID(int=1))}
        ],
    }


def test_outline_empty_document_and_display_title_field(client, fastapi_app, monkeypatch) -> None:
    document = _document(page_count=None)
    documents = SimpleNamespace(
        get=AsyncMock(return_value=document),
        get_headings=AsyncMock(return_value=[]),
        get_chunk_index=AsyncMock(return_value=[]),
        get_metadata=AsyncMock(return_value=[SimpleNamespace(field_id=7, value="Nice Title")]),
    )
    collections = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(title_field="doc_title")),
        get_schema=AsyncMock(return_value=[SimpleNamespace(id=7, field_name="doc_title")]),
    )
    _mock_reader(monkeypatch, documents, collections)

    body = client.get(f"/api/v1/documents/{document.id}/outline").json()

    assert body["headings"] == [] and body["page_count"] is None
    assert body["display_title"] == "Nice Title"


def test_outline_unknown_document_is_404(client, fastapi_app, monkeypatch) -> None:
    _mock_reader(monkeypatch, SimpleNamespace(get=AsyncMock(return_value=None)))

    assert client.get(f"/api/v1/documents/{uuid.uuid4()}/outline").status_code == 404


async def test_outline_scoped_key_foreign_is_403(fastapi_app, monkeypatch) -> None:
    from backend.routers.reading.router import get_document_outline  # noqa: PLC0415

    documents = SimpleNamespace(
        get=AsyncMock(return_value=_document(collection_id=COLL_B)),
        get_headings=AsyncMock(),
    )
    _mock_reader(monkeypatch, documents)
    with pytest.raises(HTTPException) as exc:
        await get_document_outline(document_id=uuid.uuid4(), principal=_principal(COLL_A))
    assert exc.value.status_code == 403
    documents.get_headings.assert_not_called()


# ── D-3: chunk context ───────────────────────────────────────────────────────────────────────────
def test_chunk_window_bounds_edges_and_disabled_skip(fastapi_app) -> None:
    from backend.libs.reading import ChunkWindow  # noqa: PLC0415

    entries = [
        _entry(0, []),
        _entry(1, [], role="toc"),
        _entry(2, [], override=False),
        _entry(3, [], override=False),  # the target — kept even though disabled
        _entry(4, [], role="boilerplate", override=True),
        _entry(5, []),
        _entry(6, []),
    ]
    target = entries[3].id

    window = ChunkWindow.select(entries, target, before=1, after=2)
    assert [e.chunk_index for e in window] == [0, 3, 4, 5]

    assert [e.chunk_index for e in ChunkWindow.select(entries, target, 5, 5)] == [0, 3, 4, 5, 6]
    assert [e.chunk_index for e in ChunkWindow.select(entries, entries[0].id, 2, 0)] == [0]
    assert [e.chunk_index for e in ChunkWindow.select(entries, entries[6].id, 0, 3)] == [6]
    assert ChunkWindow.select(entries, uuid.uuid4(), 1, 1) == []


def _chunk_row(index, document_id):
    return SimpleNamespace(
        id=uuid.UUID(int=index + 1),
        document_id=document_id,
        chunk_index=index,
        text=f"text {index}",
        heading_path=["S"],
        token_count=10 + index,
    )


def test_chunk_context_route_is_lean_and_flags_target(client, fastapi_app, monkeypatch) -> None:
    document = _document()
    rows = [_chunk_row(i, document.id) for i in range(4)]
    target = rows[2]
    documents = SimpleNamespace(
        get=AsyncMock(return_value=document),
        get_chunks_by_ids=AsyncMock(side_effect=lambda ids: [r for r in rows if r.id in ids]),
        get_chunk_index=AsyncMock(return_value=[_entry(i, ["S"]) for i in range(4)]),
        get_block_locations_for_chunks=AsyncMock(
            return_value={str(rows[1].id): [{"block_id": "b", "page": 4, "bbox": [0, 0, 1, 1]}]}
        ),
    )
    _mock_reader(monkeypatch, documents)

    response = client.get(f"/api/v1/chunks/{target.id}/context?before=1&after=1")

    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == str(document.id) and body["display_title"] == "Report"
    assert [c["chunk_index"] for c in body["chunks"]] == [1, 2, 3]
    assert [c["is_target"] for c in body["chunks"]] == [False, True, False]
    assert body["chunks"][0] == {
        "chunk_id": str(rows[1].id),
        "chunk_index": 1,
        "text": "text 1",
        "page_number": 5,
        "heading_path": ["S"],
        "token_count": 11,
        "is_target": False,
    }


def test_chunk_context_unknown_chunk_is_404(client, fastapi_app, monkeypatch) -> None:
    _mock_reader(monkeypatch, SimpleNamespace(get_chunks_by_ids=AsyncMock(return_value=[])))

    assert client.get(f"/api/v1/chunks/{uuid.uuid4()}/context").status_code == 404


@pytest.mark.parametrize("query", ["before=6", "after=-1"])
def test_chunk_context_bounds_are_validated(client, fastapi_app, query) -> None:
    assert client.get(f"/api/v1/chunks/{uuid.uuid4()}/context?{query}").status_code == 422


async def test_chunk_context_scoped_key_foreign_is_403(fastapi_app, monkeypatch) -> None:
    from backend.routers.reading.router import get_chunk_context  # noqa: PLC0415

    document = _document(collection_id=COLL_B)
    documents = SimpleNamespace(
        get=AsyncMock(return_value=document),
        get_chunks_by_ids=AsyncMock(return_value=[_chunk_row(0, document.id)]),
        get_chunk_index=AsyncMock(),
    )
    _mock_reader(monkeypatch, documents)
    with pytest.raises(HTTPException) as exc:
        await get_chunk_context(
            chunk_id=uuid.uuid4(), before=1, after=1, principal=_principal(COLL_A)
        )
    assert exc.value.status_code == 403
    documents.get_chunk_index.assert_not_called()


# ── D-4: chunk listing pagination + lean mode ────────────────────────────────────────────────────
def _full_chunk(index):
    return SimpleNamespace(
        id=uuid.UUID(int=index + 1),
        chunk_index=index,
        text=f"t{index}",
        token_count=3,
        is_indexed=True,
        strategy="hybrid",
        parent_id=None,
        role="body",
        enabled_override=None,
        heading_path=["H"],
    )


def _mock_chunks(monkeypatch, chunks, total):
    from backend.context import CONTEXT  # noqa: PLC0415

    documents = SimpleNamespace(
        get=AsyncMock(return_value=_document()),
        get_chunks=AsyncMock(return_value=chunks),
        count_chunks=AsyncMock(return_value=total),
        get_document_chunk_composition=AsyncMock(
            return_value=[
                SimpleNamespace(chunk_id=c.id, block_id=f"b{c.chunk_index}") for c in chunks
            ]
        ),
        get_document_chunk_metadata=AsyncMock(return_value=[]),
        get_block_locations_for_chunks=AsyncMock(
            return_value={
                str(c.id): [{"block_id": "b", "page": 1, "bbox": [0, 0, 1, 1]}] for c in chunks
            }
        ),
    )
    collections = SimpleNamespace(get_schema=AsyncMock(return_value=[]))
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(documents=documents, collections=collections)
    )
    return documents


def test_chunks_default_is_unchanged_full_shape(client, fastapi_app, monkeypatch) -> None:
    documents = _mock_chunks(monkeypatch, [_full_chunk(0), _full_chunk(1)], total=2)

    response = client.get(f"/api/v1/documents/{uuid.uuid4()}/chunks")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2 and response.headers["X-Total-Count"] == "2"
    assert set(body[0]) == {
        "id", "chunk_index", "text", "token_count", "is_indexed", "role", "enabled",
        "heading_path", "page", "page_number", "strategy", "parent_id", "block_ids", "metadata",
    }  # fmt: skip
    assert body[0]["block_ids"] == ["b0"] and body[0]["page"] == 1 and body[0]["page_number"] == 2
    documents.get_chunks.assert_awaited_once()
    assert documents.get_chunks.await_args.kwargs == {"limit": None, "offset": 0}
    documents.count_chunks.assert_not_called()


def test_chunks_limit_offset_pass_through_and_total_header(
    client, fastapi_app, monkeypatch
) -> None:
    documents = _mock_chunks(monkeypatch, [_full_chunk(3)], total=40)

    response = client.get(f"/api/v1/documents/{uuid.uuid4()}/chunks?limit=1&offset=3")

    assert response.status_code == 200
    assert [c["chunk_index"] for c in response.json()] == [3]
    assert response.headers["X-Total-Count"] == "40"
    assert documents.get_chunks.await_args.kwargs == {"limit": 1, "offset": 3}


@pytest.mark.parametrize("query", ["limit=0", "limit=501", "offset=-1"])
def test_chunks_paging_bounds_are_validated(client, fastapi_app, query) -> None:
    assert client.get(f"/api/v1/documents/{uuid.uuid4()}/chunks?{query}").status_code == 422


def test_chunks_include_geometry_false_drops_geometry(client, fastapi_app, monkeypatch) -> None:
    documents = _mock_chunks(monkeypatch, [_full_chunk(0)], total=1)

    body = client.get(f"/api/v1/documents/{uuid.uuid4()}/chunks?include_geometry=false").json()

    assert "block_ids" not in body[0] and "page" not in body[0]
    assert body[0]["page_number"] == 2 and body[0]["text"] == "t0"
    documents.get_document_chunk_composition.assert_not_called()


async def test_chunks_scoped_key_foreign_is_403(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.explorer.router import get_document_chunks  # noqa: PLC0415

    documents = SimpleNamespace(
        get=AsyncMock(return_value=_document(collection_id=COLL_B)), get_chunks=AsyncMock()
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(documents=documents))
    with pytest.raises(HTTPException) as exc:
        await get_document_chunks(
            document_id=uuid.uuid4(),
            response=SimpleNamespace(headers={}),
            limit=None,
            offset=0,
            include_geometry=True,
            principal=_principal(COLL_A),
        )
    assert exc.value.status_code == 403
    documents.get_chunks.assert_not_called()
