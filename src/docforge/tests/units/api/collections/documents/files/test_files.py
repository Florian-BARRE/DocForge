# ====== Code Summary ======
# Tests for the files section: original / markdown / pdf pre-signed URL endpoints.
# All three share the same _require_done guard (404 / 409).

import uuid

import httpx
import pytest

from backend.context import CONTEXT
from tests.units.api.conftest import make_document_orm


def _url(collection_id: uuid.UUID, document_id: uuid.UUID, artefact: str) -> str:
    return f"/api/v1/collections/{collection_id}/documents/{document_id}/{artefact}"


class TestGetOriginal:
    """GET /api/v1/collections/{collection_id}/documents/{document_id}/original"""

    @pytest.mark.asyncio
    async def test_original_returns_200_with_url(self, client: httpx.AsyncClient) -> None:
        """Done document → 200 with a presigned URL."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = make_document_orm(id=doc_id, collection_id=col_id, status="done", source_hash="abc123")
        CONTEXT.document_repo.get_by_id.return_value = doc
        CONTEXT.s3.get_presigned_url.return_value = "https://s3.example.com/orig"
        response = await client.get(_url(col_id, doc_id, "original"))
        assert response.status_code == 200
        assert response.json()["url"] == "https://s3.example.com/orig"

    @pytest.mark.asyncio
    async def test_original_returns_404_for_unknown_document(
        self, client: httpx.AsyncClient
    ) -> None:
        """Document not found → 404."""
        CONTEXT.document_repo.get_by_id.return_value = None
        response = await client.get(_url(uuid.uuid4(), uuid.uuid4(), "original"))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_original_returns_409_when_not_done(
        self, client: httpx.AsyncClient
    ) -> None:
        """Document still processing → 409 Conflict."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = make_document_orm(id=doc_id, collection_id=col_id, status="running")
        CONTEXT.document_repo.get_by_id.return_value = doc
        response = await client.get(_url(col_id, doc_id, "original"))
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_original_response_has_expires_in(
        self, client: httpx.AsyncClient
    ) -> None:
        """Response includes expires_in field (default 3600)."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = make_document_orm(id=doc_id, collection_id=col_id, status="done", source_hash="abc")
        CONTEXT.document_repo.get_by_id.return_value = doc
        body = (await client.get(_url(col_id, doc_id, "original"))).json()
        assert "expires_in" in body
        assert body["expires_in"] == 3600


class TestGetMarkdown:
    """GET /api/v1/collections/{collection_id}/documents/{document_id}/markdown"""

    @pytest.mark.asyncio
    async def test_markdown_returns_200_with_explicit_markdown_key(
        self, client: httpx.AsyncClient
    ) -> None:
        """Done doc with markdown_key in implicit_meta → 200."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = make_document_orm(
            id=doc_id, collection_id=col_id, status="done", source_hash="abc",
            implicit_meta={"markdown_key": "markdown/abc.md"},
        )
        CONTEXT.document_repo.get_by_id.return_value = doc
        CONTEXT.s3.exists.return_value = True
        response = await client.get(_url(col_id, doc_id, "markdown"))
        assert response.status_code == 200
        assert "url" in response.json()

    @pytest.mark.asyncio
    async def test_markdown_falls_back_to_s1_fingerprint(
        self, client: httpx.AsyncClient
    ) -> None:
        """No markdown_key but s1_fingerprint present → key derived, 200."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = make_document_orm(
            id=doc_id, collection_id=col_id, status="done", source_hash="abc",
            implicit_meta={"s1_fingerprint": "fp123"},
        )
        CONTEXT.document_repo.get_by_id.return_value = doc
        CONTEXT.s3.exists.return_value = True
        response = await client.get(_url(col_id, doc_id, "markdown"))
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_markdown_returns_404_when_not_in_s3(
        self, client: httpx.AsyncClient
    ) -> None:
        """Key derived but blob absent in S3 → 404."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = make_document_orm(
            id=doc_id, collection_id=col_id, status="done", source_hash="abc",
            implicit_meta={"markdown_key": "markdown/abc.md"},
        )
        CONTEXT.document_repo.get_by_id.return_value = doc
        CONTEXT.s3.exists.return_value = False
        response = await client.get(_url(col_id, doc_id, "markdown"))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_markdown_returns_404_when_no_meta(
        self, client: httpx.AsyncClient
    ) -> None:
        """No markdown_key and no s1_fingerprint → 404."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = make_document_orm(id=doc_id, collection_id=col_id, status="done", source_hash="abc", implicit_meta={})
        CONTEXT.document_repo.get_by_id.return_value = doc
        response = await client.get(_url(col_id, doc_id, "markdown"))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_markdown_returns_409_when_not_done(
        self, client: httpx.AsyncClient
    ) -> None:
        """Document not done → 409."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = make_document_orm(id=doc_id, collection_id=col_id, status="pending")
        CONTEXT.document_repo.get_by_id.return_value = doc
        response = await client.get(_url(col_id, doc_id, "markdown"))
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_markdown_returns_404_for_unknown_document(
        self, client: httpx.AsyncClient
    ) -> None:
        """Document not found → 404."""
        CONTEXT.document_repo.get_by_id.return_value = None
        response = await client.get(_url(uuid.uuid4(), uuid.uuid4(), "markdown"))
        assert response.status_code == 404


class TestGetPdf:
    """GET /api/v1/collections/{collection_id}/documents/{document_id}/pdf"""

    @pytest.mark.asyncio
    async def test_pdf_returns_200_with_url(self, client: httpx.AsyncClient) -> None:
        """Done document → 200 with a presigned URL."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = make_document_orm(id=doc_id, collection_id=col_id, status="done", source_hash="abc")
        CONTEXT.document_repo.get_by_id.return_value = doc
        CONTEXT.s3.get_presigned_url.return_value = "https://s3.example.com/abc.pdf"
        response = await client.get(_url(col_id, doc_id, "pdf"))
        assert response.status_code == 200
        assert "url" in response.json()

    @pytest.mark.asyncio
    async def test_pdf_returns_404_for_unknown_document(
        self, client: httpx.AsyncClient
    ) -> None:
        """Document not found → 404."""
        CONTEXT.document_repo.get_by_id.return_value = None
        response = await client.get(_url(uuid.uuid4(), uuid.uuid4(), "pdf"))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_pdf_returns_409_when_not_done(self, client: httpx.AsyncClient) -> None:
        """Document not done → 409."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = make_document_orm(id=doc_id, collection_id=col_id, status="failed")
        CONTEXT.document_repo.get_by_id.return_value = doc
        response = await client.get(_url(col_id, doc_id, "pdf"))
        assert response.status_code == 409
