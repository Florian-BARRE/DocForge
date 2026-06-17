# ====== Code Summary ======
# Tests for the chunks section: list / get / update.

import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from backend.context import CONTEXT
from tests.api.conftest import make_document_orm, make_chunk_row


def _base(collection_id: uuid.UUID, document_id: uuid.UUID) -> str:
    return f"/api/v1/collections/{collection_id}/documents/{document_id}/chunks"


def _list_url(collection_id: uuid.UUID, document_id: uuid.UUID) -> str:
    return _base(collection_id, document_id) + "/list"


def _get_url(collection_id: uuid.UUID, document_id: uuid.UUID, chunk_id: uuid.UUID) -> str:
    return f"{_base(collection_id, document_id)}/{chunk_id}"


def _update_url(
    collection_id: uuid.UUID, document_id: uuid.UUID, chunk_id: uuid.UUID
) -> str:
    return f"{_base(collection_id, document_id)}/{chunk_id}/update"


def _setup_doc(col_id: uuid.UUID, doc_id: uuid.UUID) -> None:
    """Wire a valid document into the document_repo mock."""
    CONTEXT.document_repo.get_by_id.return_value = make_document_orm(
        id=doc_id, collection_id=col_id
    )


class TestListChunks:
    """GET /api/v1/collections/{collection_id}/documents/{document_id}/chunks/list"""

    @pytest.mark.asyncio
    async def test_list_empty_returns_200(self, client: httpx.AsyncClient) -> None:
        """No chunks → 200 with empty list and total=0."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        _setup_doc(col_id, doc_id)
        CONTEXT.chunk_repo.get_by_document.return_value = []
        response = await client.get(_list_url(col_id, doc_id))
        assert response.status_code == 200
        body = response.json()
        assert body["chunks"] == []
        assert body["total"] == 0

    @pytest.mark.asyncio
    async def test_list_returns_chunk_rows(self, client: httpx.AsyncClient) -> None:
        """Chunks returned by repo appear in the response list."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        _setup_doc(col_id, doc_id)
        chunks = [make_chunk_row(document_id=doc_id) for _ in range(4)]
        CONTEXT.chunk_repo.get_by_document.return_value = chunks
        body = (await client.get(_list_url(col_id, doc_id))).json()
        assert body["total"] == 4
        assert len(body["chunks"]) == 4

    @pytest.mark.asyncio
    async def test_list_returns_404_for_unknown_document(
        self, client: httpx.AsyncClient
    ) -> None:
        """Document not in collection → 404."""
        CONTEXT.document_repo.get_by_id.return_value = None
        response = await client.get(_list_url(uuid.uuid4(), uuid.uuid4()))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_response_includes_pagination_fields(
        self, client: httpx.AsyncClient
    ) -> None:
        """Response has total, limit, offset in addition to chunks."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        _setup_doc(col_id, doc_id)
        CONTEXT.chunk_repo.get_by_document.return_value = []
        body = (await client.get(_list_url(col_id, doc_id))).json()
        assert "total" in body
        assert "limit" in body
        assert "offset" in body


class TestGetChunk:
    """GET /api/v1/collections/{collection_id}/documents/{document_id}/chunks/{chunk_id}"""

    @pytest.mark.asyncio
    async def test_get_returns_200_with_chunk_fields(
        self, client: httpx.AsyncClient
    ) -> None:
        """Known chunk returns 200 with required fields."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        chunk_id = uuid.uuid4()
        _setup_doc(col_id, doc_id)
        CONTEXT.chunk_repo.get_by_id.return_value = make_chunk_row(
            id=chunk_id, document_id=doc_id
        )
        response = await client.get(_get_url(col_id, doc_id, chunk_id))
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_returns_404_for_unknown_chunk(
        self, client: httpx.AsyncClient
    ) -> None:
        """Chunk not in repo → 404."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        _setup_doc(col_id, doc_id)
        CONTEXT.chunk_repo.get_by_id.return_value = None
        response = await client.get(_get_url(col_id, doc_id, uuid.uuid4()))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_returns_404_when_chunk_belongs_to_different_document(
        self, client: httpx.AsyncClient
    ) -> None:
        """Chunk exists but belongs to a different document → 404."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        _setup_doc(col_id, doc_id)
        chunk_id = uuid.uuid4()
        # Chunk belongs to a different document
        CONTEXT.chunk_repo.get_by_id.return_value = make_chunk_row(
            id=chunk_id, document_id=uuid.uuid4()
        )
        response = await client.get(_get_url(col_id, doc_id, chunk_id))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_response_has_required_fields(
        self, client: httpx.AsyncClient
    ) -> None:
        """Response exposes id, document_id, raw_text, embed_text, strategy, prov."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        chunk_id = uuid.uuid4()
        _setup_doc(col_id, doc_id)
        CONTEXT.chunk_repo.get_by_id.return_value = make_chunk_row(
            id=chunk_id, document_id=doc_id, strategy="recursive_structure_aware"
        )
        body = (await client.get(_get_url(col_id, doc_id, chunk_id))).json()
        for field in ("id", "document_id", "raw_text", "embed_text", "strategy", "prov"):
            assert field in body, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_get_strategy_field_value(self, client: httpx.AsyncClient) -> None:
        """Strategy field echoes the stored value."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        chunk_id = uuid.uuid4()
        _setup_doc(col_id, doc_id)
        CONTEXT.chunk_repo.get_by_id.return_value = make_chunk_row(
            id=chunk_id, document_id=doc_id, strategy="fixed_size"
        )
        body = (await client.get(_get_url(col_id, doc_id, chunk_id))).json()
        assert body["strategy"] == "fixed_size"


class TestUpdateChunk:
    """POST /api/v1/collections/{collection_id}/documents/{document_id}/chunks/{chunk_id}/update"""

    def _setup(self, col_id: uuid.UUID, doc_id: uuid.UUID, chunk_id: uuid.UUID) -> None:
        """Wire document and chunk mocks for a successful update."""
        _setup_doc(col_id, doc_id)
        CONTEXT.chunk_repo.get_by_id.return_value = make_chunk_row(
            id=chunk_id, document_id=doc_id
        )
        CONTEXT.chunk_repo.update.return_value = {
            "id": str(chunk_id),
            "raw_text": "Corrected text.",
            "embed_text": "Title\nCorrected text.",
        }

    @pytest.mark.asyncio
    async def test_update_raw_text_returns_200(self, client: httpx.AsyncClient) -> None:
        """Providing only raw_text is valid → 200."""
        col_id, doc_id, chunk_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        self._setup(col_id, doc_id, chunk_id)
        response = await client.post(
            _update_url(col_id, doc_id, chunk_id),
            json={"raw_text": "Corrected text."},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_embed_text_returns_200(self, client: httpx.AsyncClient) -> None:
        """Providing only embed_text is valid → 200."""
        col_id, doc_id, chunk_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        self._setup(col_id, doc_id, chunk_id)
        response = await client.post(
            _update_url(col_id, doc_id, chunk_id),
            json={"embed_text": "New embed text."},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_both_null_returns_422(self, client: httpx.AsyncClient) -> None:
        """Neither raw_text nor embed_text provided → 422."""
        col_id, doc_id, chunk_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        _setup_doc(col_id, doc_id)
        CONTEXT.chunk_repo.get_by_id.return_value = make_chunk_row(
            id=chunk_id, document_id=doc_id
        )
        response = await client.post(
            _update_url(col_id, doc_id, chunk_id),
            json={"reindex": False},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_reindex_without_indexer_returns_warning(
        self, client: httpx.AsyncClient
    ) -> None:
        """reindex=True with metadata_indexer=None → reindexed=False + warning."""
        col_id, doc_id, chunk_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        self._setup(col_id, doc_id, chunk_id)
        # metadata_indexer is already set to None by inject_context
        body = (
            await client.post(
                _update_url(col_id, doc_id, chunk_id),
                json={"raw_text": "New text.", "reindex": True},
            )
        ).json()
        assert body["reindexed"] is False
        assert body["warning"] is not None

    @pytest.mark.asyncio
    async def test_update_reindex_with_indexer_sets_reindexed_true(
        self, client: httpx.AsyncClient
    ) -> None:
        """reindex=True with a live metadata_indexer → reindexed=True."""
        col_id, doc_id, chunk_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        self._setup(col_id, doc_id, chunk_id)
        mock_indexer = MagicMock()
        mock_indexer.reembed_content = AsyncMock()
        CONTEXT.metadata_indexer = mock_indexer
        body = (
            await client.post(
                _update_url(col_id, doc_id, chunk_id),
                json={"raw_text": "New text.", "reindex": True},
            )
        ).json()
        assert body["reindexed"] is True
        assert body["warning"] is None

    @pytest.mark.asyncio
    async def test_update_returns_404_for_unknown_document(
        self, client: httpx.AsyncClient
    ) -> None:
        """Document not in collection → 404."""
        CONTEXT.document_repo.get_by_id.return_value = None
        response = await client.post(
            _update_url(uuid.uuid4(), uuid.uuid4(), uuid.uuid4()),
            json={"raw_text": "text"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_returns_404_for_unknown_chunk(
        self, client: httpx.AsyncClient
    ) -> None:
        """Chunk not found in document → 404."""
        col_id, doc_id = uuid.uuid4(), uuid.uuid4()
        _setup_doc(col_id, doc_id)
        CONTEXT.chunk_repo.get_by_id.return_value = None
        response = await client.post(
            _update_url(col_id, doc_id, uuid.uuid4()),
            json={"raw_text": "text"},
        )
        assert response.status_code == 404
