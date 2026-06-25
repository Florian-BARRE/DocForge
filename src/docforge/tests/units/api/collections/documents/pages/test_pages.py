# ====== Code Summary ======
# Tests for the pages section: list / get / screenshot / reingest.
# Pages are a derived view over a document's blocks — not stored entities.

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.context import CONTEXT
from tests.units.api.conftest import make_document_orm


def _base(collection_id: uuid.UUID, document_id: uuid.UUID) -> str:
    return f"/api/v1/collections/{collection_id}/documents/{document_id}/pages"


def _list_url(c: uuid.UUID, d: uuid.UUID) -> str:
    return f"{_base(c, d)}/list"


def _get_url(c: uuid.UUID, d: uuid.UUID, page: int) -> str:
    return f"{_base(c, d)}/{page}"


def _screenshot_url(c: uuid.UUID, d: uuid.UUID, page: int) -> str:
    return f"{_base(c, d)}/{page}/screenshot"


def _reingest_url(c: uuid.UUID, d: uuid.UUID, page: int) -> str:
    return f"{_base(c, d)}/{page}/reingest"


def _make_block(page: int = 1, block_type: str = "text", text: str = "Block text.") -> MagicMock:
    """Return a minimal mock block object."""
    b = MagicMock()
    b.id = str(uuid.uuid4())
    b.page = page
    b.type = block_type
    b.text = text
    b.bbox = [0.0, 0.0, 100.0, 20.0]
    return b


class TestListPages:
    """GET /api/v1/collections/{collection_id}/documents/{document_id}/pages/list"""

    @pytest.mark.asyncio
    async def test_list_empty_blocks_returns_200(self, client: httpx.AsyncClient) -> None:
        """No blocks → 200 with empty pages list."""
        c, d = uuid.uuid4(), uuid.uuid4()
        CONTEXT.document_repo.get_by_id.return_value = make_document_orm(id=d, collection_id=c)
        CONTEXT.block_repo.get_by_document.return_value = []
        CONTEXT.chunk_repo.get_by_document.return_value = []
        response = await client.get(_list_url(c, d))
        assert response.status_code == 200
        body = response.json()
        assert body["total_pages"] == 0
        assert body["pages"] == []

    @pytest.mark.asyncio
    async def test_list_aggregates_blocks_per_page(self, client: httpx.AsyncClient) -> None:
        """Two blocks on page 1 and one on page 2 → 2 page entries."""
        c, d = uuid.uuid4(), uuid.uuid4()
        CONTEXT.document_repo.get_by_id.return_value = make_document_orm(id=d, collection_id=c)
        CONTEXT.block_repo.get_by_document.return_value = [
            _make_block(page=1),
            _make_block(page=1),
            _make_block(page=2),
        ]
        CONTEXT.chunk_repo.get_by_document.return_value = []
        body = (await client.get(_list_url(c, d))).json()
        assert body["total_pages"] == 2
        page1 = next(p for p in body["pages"] if p["page"] == 1)
        assert page1["n_blocks"] == 2

    @pytest.mark.asyncio
    async def test_list_returns_404_for_unknown_document(
        self, client: httpx.AsyncClient
    ) -> None:
        """Document not in collection → 404."""
        CONTEXT.document_repo.get_by_id.return_value = None
        response = await client.get(_list_url(uuid.uuid4(), uuid.uuid4()))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_page_info_has_required_fields(
        self, client: httpx.AsyncClient
    ) -> None:
        """Each page entry has page, n_blocks, n_figures, n_tables, has_text, n_chunks."""
        c, d = uuid.uuid4(), uuid.uuid4()
        CONTEXT.document_repo.get_by_id.return_value = make_document_orm(id=d, collection_id=c)
        CONTEXT.block_repo.get_by_document.return_value = [_make_block(page=1)]
        CONTEXT.chunk_repo.get_by_document.return_value = []
        body = (await client.get(_list_url(c, d))).json()
        entry = body["pages"][0]
        for field in ("page", "n_blocks", "n_figures", "n_tables", "has_text", "n_chunks"):
            assert field in entry, f"Missing field: {field}"


class TestGetPage:
    """GET /api/v1/collections/{collection_id}/documents/{document_id}/pages/{page_number}"""

    @pytest.mark.asyncio
    async def test_get_page_returns_200(self, client: httpx.AsyncClient) -> None:
        """Known document + page → 200."""
        c, d = uuid.uuid4(), uuid.uuid4()
        CONTEXT.document_repo.get_by_id.return_value = make_document_orm(id=d, collection_id=c)
        CONTEXT.block_repo.get_by_document.return_value = [_make_block(page=1)]
        CONTEXT.chunk_repo.get_by_document.return_value = []
        response = await client.get(_get_url(c, d, 1))
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_page_returns_404_for_unknown_document(
        self, client: httpx.AsyncClient
    ) -> None:
        """Document not in collection → 404."""
        CONTEXT.document_repo.get_by_id.return_value = None
        response = await client.get(_get_url(uuid.uuid4(), uuid.uuid4(), 1))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_page_response_shape(self, client: httpx.AsyncClient) -> None:
        """Response has page, n_blocks, blocks, text, chunk_ids."""
        c, d = uuid.uuid4(), uuid.uuid4()
        CONTEXT.document_repo.get_by_id.return_value = make_document_orm(id=d, collection_id=c)
        CONTEXT.block_repo.get_by_document.return_value = [
            _make_block(page=3, text="Intro paragraph.")
        ]
        CONTEXT.chunk_repo.get_by_document.return_value = []
        body = (await client.get(_get_url(c, d, 3))).json()
        assert body["page"] == 3
        assert body["n_blocks"] == 1
        assert "blocks" in body
        assert "text" in body
        assert "chunk_ids" in body

    @pytest.mark.asyncio
    async def test_get_page_text_concatenates_blocks(
        self, client: httpx.AsyncClient
    ) -> None:
        """Page text is the concatenation of all block texts on that page."""
        c, d = uuid.uuid4(), uuid.uuid4()
        CONTEXT.document_repo.get_by_id.return_value = make_document_orm(id=d, collection_id=c)
        CONTEXT.block_repo.get_by_document.return_value = [
            _make_block(page=1, text="First block."),
            _make_block(page=1, text="Second block."),
        ]
        CONTEXT.chunk_repo.get_by_document.return_value = []
        body = (await client.get(_get_url(c, d, 1))).json()
        assert "First block." in body["text"]
        assert "Second block." in body["text"]


_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"  # Standard PNG header

_RENDER_PATH = "backend.routers.collections.documents.pages.router._render_page_png"


class TestGetPageScreenshot:
    """GET /api/v1/collections/{collection_id}/documents/{document_id}/pages/{page_number}/screenshot
    Page PNGs are rendered on-the-fly from the PDF artefact in S3.
    The route prefers the Gotenberg-converted PDF (key_pdf) so that non-PDF originals
    (pptx/docx/html) are rendered page-faithfully.  key_original is used only as a fallback.
    """

    @pytest.mark.asyncio
    async def test_screenshot_returns_200_as_png(self, client: httpx.AsyncClient) -> None:
        """Done doc + PDF in S3 → 200 with image/png content."""
        c, d = uuid.uuid4(), uuid.uuid4()
        CONTEXT.document_repo.get_by_id.return_value = make_document_orm(
            id=d, collection_id=c, status="done", source_hash="abc"
        )
        CONTEXT.s3.exists.return_value = True
        CONTEXT.s3.download.return_value = b"fake_pdf"
        with patch(_RENDER_PATH, return_value=_PNG_MAGIC):
            response = await client.get(_screenshot_url(c, d, 1))
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.content == _PNG_MAGIC

    @pytest.mark.asyncio
    async def test_screenshot_prefers_key_pdf_over_key_original(
        self, client: httpx.AsyncClient
    ) -> None:
        """Route must try S3Helpers.key_pdf first (Gotenberg-converted PDF).

        For non-PDF originals (pptx/docx/html), the raw original file is not a PDF, so
        PyMuPDF would mis-count pages or fail entirely.  The converted PDF always has the
        correct page structure.  This test pins that S3 is queried with the pdf key first.
        """
        from unittest.mock import call
        from common_libs.storage.s3.helpers import S3Helpers

        c, d = uuid.uuid4(), uuid.uuid4()
        source_hash = "sha256abc"
        CONTEXT.document_repo.get_by_id.return_value = make_document_orm(
            id=d, collection_id=c, status="done", source_hash=source_hash
        )
        # First exists call (key_pdf) returns True → route should download key_pdf, not key_original.
        CONTEXT.s3.exists.return_value = True
        CONTEXT.s3.download.return_value = b"fake_pdf_bytes"
        with patch(_RENDER_PATH, return_value=_PNG_MAGIC):
            response = await client.get(_screenshot_url(c, d, 0))
        assert response.status_code == 200
        expected_pdf_key = S3Helpers.key_pdf(source_hash)
        # The first s3.exists call must use key_pdf — assert it appears as the very first call.
        first_exists_call = CONTEXT.s3.exists.await_args_list[0]
        assert first_exists_call == call(expected_pdf_key)
        # And download must use the same key_pdf (not the original).
        CONTEXT.s3.download.assert_awaited_once_with(expected_pdf_key)

    @pytest.mark.asyncio
    async def test_screenshot_falls_back_to_key_original_when_pdf_missing(
        self, client: httpx.AsyncClient
    ) -> None:
        """When key_pdf is absent, route falls back to key_original.

        PDF-native documents may not have a separate converted-PDF artefact (the original
        IS the PDF), so the fallback path must work correctly.
        """
        from unittest.mock import call
        from common_libs.storage.s3.helpers import S3Helpers

        c, d = uuid.uuid4(), uuid.uuid4()
        source_hash = "sha256xyz"
        CONTEXT.document_repo.get_by_id.return_value = make_document_orm(
            id=d, collection_id=c, status="done", source_hash=source_hash
        )
        # key_pdf missing, key_original present.
        CONTEXT.s3.exists.side_effect = [False, True]
        CONTEXT.s3.download.return_value = b"native_pdf_bytes"
        with patch(_RENDER_PATH, return_value=_PNG_MAGIC):
            response = await client.get(_screenshot_url(c, d, 0))
        assert response.status_code == 200
        expected_original_key = S3Helpers.key_original(source_hash)
        expected_pdf_key = S3Helpers.key_pdf(source_hash)
        # First call: try key_pdf, second call: try key_original.
        assert CONTEXT.s3.exists.await_args_list == [
            call(expected_pdf_key),
            call(expected_original_key),
        ]
        # Download uses the fallback key_original.
        CONTEXT.s3.download.assert_awaited_once_with(expected_original_key)

    @pytest.mark.asyncio
    async def test_screenshot_returns_409_when_not_done(
        self, client: httpx.AsyncClient
    ) -> None:
        """Document not done → 409 Conflict."""
        c, d = uuid.uuid4(), uuid.uuid4()
        CONTEXT.document_repo.get_by_id.return_value = make_document_orm(
            id=d, collection_id=c, status="running"
        )
        response = await client.get(_screenshot_url(c, d, 1))
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_screenshot_returns_404_when_pdf_missing_in_s3(
        self, client: httpx.AsyncClient
    ) -> None:
        """Done doc but original PDF not in S3 → 404."""
        c, d = uuid.uuid4(), uuid.uuid4()
        CONTEXT.document_repo.get_by_id.return_value = make_document_orm(
            id=d, collection_id=c, status="done", source_hash="abc"
        )
        CONTEXT.s3.exists.return_value = False
        response = await client.get(_screenshot_url(c, d, 1))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_screenshot_returns_404_for_out_of_range_page(
        self, client: httpx.AsyncClient
    ) -> None:
        """Renderer raises ValueError for out-of-range page → 404."""
        c, d = uuid.uuid4(), uuid.uuid4()
        CONTEXT.document_repo.get_by_id.return_value = make_document_orm(
            id=d, collection_id=c, status="done", source_hash="abc"
        )
        CONTEXT.s3.exists.return_value = True
        CONTEXT.s3.download.return_value = b"fake_pdf"
        with patch(_RENDER_PATH, side_effect=ValueError("Page 99 out of range")):
            response = await client.get(_screenshot_url(c, d, 99))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_screenshot_returns_404_for_unknown_document(
        self, client: httpx.AsyncClient
    ) -> None:
        """Document not in collection → 404."""
        CONTEXT.document_repo.get_by_id.return_value = None
        response = await client.get(_screenshot_url(uuid.uuid4(), uuid.uuid4(), 1))
        assert response.status_code == 404


class TestReingestPage:
    """POST /api/v1/collections/{collection_id}/documents/{document_id}/pages/{page_number}/reingest"""

    @pytest.mark.asyncio
    async def test_reingest_page_returns_200(self, client: httpx.AsyncClient) -> None:
        """Valid document → 200 (full document re-run, page is only a view)."""
        c, d = uuid.uuid4(), uuid.uuid4()
        job = MagicMock()
        job.id = uuid.uuid4()
        CONTEXT.document_repo.get_by_id.return_value = make_document_orm(
            id=d, collection_id=c
        )
        CONTEXT.job_repo.create.return_value = job
        response = await client.post(_reingest_url(c, d, 2))
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_reingest_page_returns_404_for_unknown_document(
        self, client: httpx.AsyncClient
    ) -> None:
        """Document not in collection → 404."""
        CONTEXT.document_repo.get_by_id.return_value = None
        response = await client.post(_reingest_url(uuid.uuid4(), uuid.uuid4(), 1))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_reingest_page_response_has_page_and_note(
        self, client: httpx.AsyncClient
    ) -> None:
        """Response includes page number and an explanatory note."""
        c, d = uuid.uuid4(), uuid.uuid4()
        job = MagicMock()
        job.id = uuid.uuid4()
        CONTEXT.document_repo.get_by_id.return_value = make_document_orm(
            id=d, collection_id=c
        )
        CONTEXT.job_repo.create.return_value = job
        body = (await client.post(_reingest_url(c, d, 3))).json()
        assert body["page"] == 3
        assert "note" in body
        assert len(body["note"]) > 0

    @pytest.mark.asyncio
    async def test_reingest_page_always_uses_force_true(
        self, client: httpx.AsyncClient
    ) -> None:
        """Page reingest always invalidates the node cache (force=True)."""
        c, d = uuid.uuid4(), uuid.uuid4()
        job = MagicMock()
        job.id = uuid.uuid4()
        CONTEXT.document_repo.get_by_id.return_value = make_document_orm(
            id=d, collection_id=c
        )
        CONTEXT.job_repo.create.return_value = job
        await client.post(_reingest_url(c, d, 1))
        CONTEXT.node_cache.invalidate_document.assert_called_once()


class TestPagesCrossCollectionScope:
    """
    Cross-collection IDOR guard: ``_require_document`` in the pages router checks
    that ``doc.collection_id == path collection_id``.

    A document in the DB that belongs to a DIFFERENT collection must be rejected
    with 404 across all pages endpoints (list, detail, screenshot, reingest).
    """

    @pytest.mark.asyncio
    async def test_list_rejects_doc_from_different_collection(
        self, client: httpx.AsyncClient
    ) -> None:
        """doc.collection_id != path → 404 on pages/list."""
        path_col = uuid.uuid4()
        doc_col = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = make_document_orm(id=doc_id, collection_id=doc_col)
        CONTEXT.document_repo.get_by_id.return_value = doc
        response = await client.get(_list_url(path_col, doc_id))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_detail_rejects_doc_from_different_collection(
        self, client: httpx.AsyncClient
    ) -> None:
        """doc.collection_id != path → 404 on pages/{n}."""
        path_col = uuid.uuid4()
        doc_col = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = make_document_orm(id=doc_id, collection_id=doc_col)
        CONTEXT.document_repo.get_by_id.return_value = doc
        response = await client.get(_get_url(path_col, doc_id, 0))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_screenshot_rejects_doc_from_different_collection(
        self, client: httpx.AsyncClient
    ) -> None:
        """doc.collection_id != path → 404 on pages/{n}/screenshot."""
        path_col = uuid.uuid4()
        doc_col = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = make_document_orm(id=doc_id, collection_id=doc_col)
        CONTEXT.document_repo.get_by_id.return_value = doc
        response = await client.get(_screenshot_url(path_col, doc_id, 0))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_reingest_rejects_doc_from_different_collection(
        self, client: httpx.AsyncClient
    ) -> None:
        """doc.collection_id != path → 404 on pages/{n}/reingest."""
        path_col = uuid.uuid4()
        doc_col = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = make_document_orm(id=doc_id, collection_id=doc_col)
        CONTEXT.document_repo.get_by_id.return_value = doc
        response = await client.post(_reingest_url(path_col, doc_id, 0))
        assert response.status_code == 404
