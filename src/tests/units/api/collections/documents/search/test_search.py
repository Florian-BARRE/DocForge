# ====== Code Summary ======
# Tests for the search section: collection-wide search and per-document search.

import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from backend.context import CONTEXT
from tests.units.api.conftest import make_collection_orm, make_document_orm


def _col_search_url(collection_id: uuid.UUID) -> str:
    return f"/api/v1/collections/{collection_id}/documents/search"


def _doc_search_url(collection_id: uuid.UUID, document_id: uuid.UUID) -> str:
    return f"/api/v1/collections/{collection_id}/documents/{document_id}/search"


def _make_search_result() -> MagicMock:
    """Return a minimal mock SearchResult compatible with _item()."""
    r = MagicMock()
    r.chunk_id = str(uuid.uuid4())
    r.document_id = str(uuid.uuid4())
    r.score = 0.9
    r.raw_text = "Test chunk text."
    r.strategy = "recursive_structure_aware"
    r.token_count = 5
    r.pages = [1]
    r.block_ids = ["blk1"]
    return r


class TestSearchCollection:
    """POST /api/v1/collections/{collection_id}/documents/search"""

    @pytest.mark.asyncio
    async def test_search_disabled_returns_empty_200(self, client: httpx.AsyncClient) -> None:
        """retrieval=None (S6 disabled) → 200 with empty graceful-degradation response (no 503)."""
        original = CONTEXT.retrieval
        CONTEXT.retrieval = None
        try:
            response = await client.post(
                _col_search_url(uuid.uuid4()), json={"query": "test"}
            )
            assert response.status_code == 200
            body = response.json()
            assert body["total"] == 0
            assert body["results"] == []
            assert "note" in body and body["note"]
        finally:
            CONTEXT.retrieval = original

    @pytest.mark.asyncio
    async def test_search_missing_collection_returns_404(
        self, client: httpx.AsyncClient
    ) -> None:
        """404 when the collection does not exist."""
        CONTEXT.collection_repo.get_by_id.return_value = None
        response = await client.post(
            _col_search_url(uuid.uuid4()), json={"query": "test"}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_search_empty_results_returns_200(
        self, client: httpx.AsyncClient
    ) -> None:
        """Collection exists but no results → 200 with empty list."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(id=col_id)
        CONTEXT.retrieval.search.return_value = []
        response = await client.post(
            _col_search_url(col_id), json={"query": "test query"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 0
        assert body["results"] == []

    @pytest.mark.asyncio
    async def test_search_response_has_required_fields(
        self, client: httpx.AsyncClient
    ) -> None:
        """Response contains collection_id, query, total, results."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(id=col_id)
        CONTEXT.retrieval.search.return_value = []
        body = (
            await client.post(_col_search_url(col_id), json={"query": "anything"})
        ).json()
        assert "collection_id" in body
        assert "query" in body
        assert "total" in body
        assert "results" in body

    @pytest.mark.asyncio
    async def test_search_with_results_returns_chunk_fields(
        self, client: httpx.AsyncClient
    ) -> None:
        """Each result item has chunk_id, document_id, score, raw_text, strategy."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(id=col_id)
        CONTEXT.retrieval.search.return_value = [_make_search_result()]
        body = (
            await client.post(_col_search_url(col_id), json={"query": "test"})
        ).json()
        assert body["total"] == 1
        item = body["results"][0]
        for field in ("chunk_id", "document_id", "score", "raw_text", "strategy"):
            assert field in item, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_search_missing_query_returns_422(
        self, client: httpx.AsyncClient
    ) -> None:
        """Body without 'query' fails Pydantic validation → 422."""
        response = await client.post(
            _col_search_url(uuid.uuid4()), json={}
        )
        assert response.status_code == 422


class TestSearchWithinDocument:
    """POST /api/v1/collections/{collection_id}/documents/{document_id}/search"""

    @pytest.mark.asyncio
    async def test_search_disabled_returns_empty_200(self, client: httpx.AsyncClient) -> None:
        """retrieval=None → 200 with empty graceful-degradation response (no 503)."""
        original = CONTEXT.retrieval
        CONTEXT.retrieval = None
        try:
            response = await client.post(
                _doc_search_url(uuid.uuid4(), uuid.uuid4()), json={"query": "test"}
            )
            assert response.status_code == 200
            body = response.json()
            assert body["total"] == 0
            assert body["results"] == []
            assert "note" in body and body["note"]
        finally:
            CONTEXT.retrieval = original

    @pytest.mark.asyncio
    async def test_search_missing_document_returns_404(
        self, client: httpx.AsyncClient
    ) -> None:
        """Document not found → 404."""
        CONTEXT.document_repo.get_by_id.return_value = None
        response = await client.post(
            _doc_search_url(uuid.uuid4(), uuid.uuid4()), json={"query": "test"}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_search_wrong_collection_returns_404(
        self, client: httpx.AsyncClient
    ) -> None:
        """Document belongs to a different collection → 404."""
        col_id = uuid.uuid4()
        doc = make_document_orm(collection_id=uuid.uuid4())  # different collection
        CONTEXT.document_repo.get_by_id.return_value = doc
        response = await client.post(
            _doc_search_url(col_id, uuid.uuid4()), json={"query": "test"}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_search_pinned_to_document_returns_200(
        self, client: httpx.AsyncClient
    ) -> None:
        """Happy path: doc found, retrieval enabled, 200 with results."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = make_document_orm(id=doc_id, collection_id=col_id)
        CONTEXT.document_repo.get_by_id.return_value = doc
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(id=col_id)
        CONTEXT.retrieval.search.return_value = [_make_search_result()]
        response = await client.post(
            _doc_search_url(col_id, doc_id), json={"query": "pinned"}
        )
        assert response.status_code == 200
        assert response.json()["total"] == 1

    @pytest.mark.asyncio
    async def test_search_passes_pinned_filter(self, client: httpx.AsyncClient) -> None:
        """The per-document search adds a must-clause with the document_id."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = make_document_orm(id=doc_id, collection_id=col_id)
        CONTEXT.document_repo.get_by_id.return_value = doc
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(id=col_id)
        CONTEXT.retrieval.search.return_value = []
        await client.post(
            _doc_search_url(col_id, doc_id), json={"query": "q"}
        )
        call_kwargs = CONTEXT.retrieval.search.call_args[1]
        assert "payload_filter" in call_kwargs
        must = call_kwargs["payload_filter"].get("must", [])
        assert any(
            c.get("key") == "document_id" and c.get("match", {}).get("value") == str(doc_id)
            for c in must
        )


class TestSearchServiceUnavailable:
    """503 — the embed/vector backend is wired but unreachable or misconfigured."""

    @pytest.mark.asyncio
    async def test_collection_search_embed_unreachable_returns_503(
        self, client: httpx.AsyncClient
    ) -> None:
        """A ConnectError from the retrieval/embed call surfaces as 503 (service unavailable)."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(id=col_id)
        # The engine delegates to retrieval.search; an unreachable embed/Qdrant raises ConnectError.
        CONTEXT.retrieval.search = AsyncMock(side_effect=httpx.ConnectError("embed unreachable"))
        response = await client.post(_col_search_url(col_id), json={"query": "test"})
        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_collection_search_provider_not_configured_returns_503(
        self, client: httpx.AsyncClient
    ) -> None:
        """build_search_pipeline raising ValueError (no provider) → 503."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(id=col_id)
        CONTEXT.registry.build_search_pipeline = MagicMock(
            side_effect=ValueError("embed provider not configured")
        )
        response = await client.post(_col_search_url(col_id), json={"query": "test"})
        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_document_search_embed_unreachable_returns_503(
        self, client: httpx.AsyncClient
    ) -> None:
        """The per-document search surfaces an embed/Qdrant outage as 503 too."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        CONTEXT.document_repo.get_by_id.return_value = make_document_orm(id=doc_id, collection_id=col_id)
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(id=col_id)
        CONTEXT.retrieval.search = AsyncMock(side_effect=httpx.TimeoutException("qdrant timeout"))
        response = await client.post(_doc_search_url(col_id, doc_id), json={"query": "test"})
        assert response.status_code == 503
