# ====== Code Summary ======
# Tests for the documents section: ingest / list / get / update / reingest / delete.

import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from backend.context import CONTEXT
from tests.api.conftest import make_collection_orm, make_document_orm


def _col_url(collection_id: uuid.UUID, suffix: str = "") -> str:
    return f"/api/v1/collections/{collection_id}/documents{suffix}"


def _doc_url(collection_id: uuid.UUID, document_id: uuid.UUID, suffix: str = "") -> str:
    return f"/api/v1/collections/{collection_id}/documents/{document_id}{suffix}"


def _pdf_file(size: int = 100) -> bytes:
    return b"%PDF-1.4 " + b"x" * size


# ─────────────────────────── Ingest ─────────────────────────────


class TestIngestDocument:
    """POST /api/v1/collections/{collection_id}/documents/ingest"""

    @pytest.mark.asyncio
    async def test_ingest_new_document_returns_202(self, client: httpx.AsyncClient) -> None:
        """New document is accepted and enqueued → 202."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        job = MagicMock()
        job.id = uuid.uuid4()
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(id=col_id)
        CONTEXT.document_repo.find_duplicate.return_value = None
        CONTEXT.document_repo.create.return_value = make_document_orm(
            id=doc_id, collection_id=col_id, status="pending"
        )
        CONTEXT.job_repo.create.return_value = job
        response = await client.post(
            _col_url(col_id, "/ingest"),
            files={"file": ("report.pdf", _pdf_file(), "application/pdf")},
        )
        assert response.status_code == 202

    @pytest.mark.asyncio
    async def test_ingest_response_has_doc_id_and_job_id(
        self, client: httpx.AsyncClient
    ) -> None:
        """Response body contains doc_id, job_id, status, duplicate."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        job_id = uuid.uuid4()
        job = MagicMock()
        job.id = job_id
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(id=col_id)
        CONTEXT.document_repo.find_duplicate.return_value = None
        CONTEXT.document_repo.create.return_value = make_document_orm(
            id=doc_id, collection_id=col_id, status="pending"
        )
        CONTEXT.job_repo.create.return_value = job
        response = await client.post(
            _col_url(col_id, "/ingest"),
            files={"file": ("report.pdf", _pdf_file(), "application/pdf")},
        )
        body = response.json()
        assert "doc_id" in body
        assert "job_id" in body
        assert body["duplicate"] is False
        assert body["status"] == "pending"

    @pytest.mark.asyncio
    async def test_ingest_duplicate_returns_202_with_flag(
        self, client: httpx.AsyncClient
    ) -> None:
        """Already-ingested content returns 202 with duplicate=True."""
        col_id = uuid.uuid4()
        existing = make_document_orm(status="done")
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(id=col_id)
        CONTEXT.document_repo.find_duplicate.return_value = existing
        response = await client.post(
            _col_url(col_id, "/ingest"),
            files={"file": ("report.pdf", _pdf_file(), "application/pdf")},
        )
        assert response.status_code == 202
        assert response.json()["duplicate"] is True

    @pytest.mark.asyncio
    async def test_ingest_missing_collection_returns_404(
        self, client: httpx.AsyncClient
    ) -> None:
        """Unknown collection_id → 404."""
        CONTEXT.collection_repo.get_by_id.return_value = None
        response = await client.post(
            _col_url(uuid.uuid4(), "/ingest"),
            files={"file": ("report.pdf", _pdf_file(), "application/pdf")},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_ingest_empty_file_returns_400(self, client: httpx.AsyncClient) -> None:
        """Zero-byte file → 400 before any collection/format check."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(id=col_id)
        response = await client.post(
            _col_url(col_id, "/ingest"),
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_ingest_unsupported_format_returns_415(
        self, client: httpx.AsyncClient
    ) -> None:
        """Format not in supported_formats → 415 from AdmissionValidator."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(
            id=col_id, supported_formats=["pdf"]
        )
        response = await client.post(
            _col_url(col_id, "/ingest"),
            files={"file": ("image.png", b"PNG_DATA", "image/png")},
        )
        assert response.status_code == 415

    @pytest.mark.asyncio
    async def test_ingest_oversized_file_returns_413(
        self, client: httpx.AsyncClient
    ) -> None:
        """File exceeding max_file_size_bytes → 413."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(
            id=col_id, supported_formats=["pdf"], max_file_size_bytes=1
        )
        response = await client.post(
            _col_url(col_id, "/ingest"),
            files={"file": ("big.pdf", _pdf_file(size=100), "application/pdf")},
        )
        assert response.status_code == 413

    @pytest.mark.asyncio
    async def test_ingest_invalid_metadata_json_returns_422(
        self, client: httpx.AsyncClient
    ) -> None:
        """Metadata form field that is not valid JSON → 422."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(id=col_id)
        response = await client.post(
            _col_url(col_id, "/ingest"),
            files={"file": ("report.pdf", _pdf_file(), "application/pdf")},
            data={"metadata": "not-json"},
        )
        assert response.status_code == 422


# ─────────────────────────── List ─────────────────────────────


class TestListDocuments:
    """GET /api/v1/collections/{collection_id}/documents/list"""

    @pytest.mark.asyncio
    async def test_list_returns_200_for_known_collection(
        self, client: httpx.AsyncClient
    ) -> None:
        """200 when the collection exists."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(id=col_id)
        CONTEXT.document_repo.count_by_collection.return_value = 0
        CONTEXT.document_repo.list_by_collection.return_value = []
        response = await client.get(_col_url(col_id, "/list"))
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_returns_404_for_missing_collection(
        self, client: httpx.AsyncClient
    ) -> None:
        """404 when the collection does not exist."""
        CONTEXT.collection_repo.get_by_id.return_value = None
        response = await client.get(_col_url(uuid.uuid4(), "/list"))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_response_shape(self, client: httpx.AsyncClient) -> None:
        """Response has documents[], total, limit, offset."""
        col_id = uuid.uuid4()
        docs = [make_document_orm(collection_id=col_id) for _ in range(3)]
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(id=col_id)
        CONTEXT.document_repo.count_by_collection.return_value = 3
        CONTEXT.document_repo.list_by_collection.return_value = docs
        body = (await client.get(_col_url(col_id, "/list"))).json()
        assert body["total"] == 3
        assert len(body["documents"]) == 3
        assert "limit" in body
        assert "offset" in body

    @pytest.mark.asyncio
    async def test_list_default_pagination(self, client: httpx.AsyncClient) -> None:
        """Default limit=100, offset=0 are applied."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(id=col_id)
        CONTEXT.document_repo.count_by_collection.return_value = 0
        CONTEXT.document_repo.list_by_collection.return_value = []
        body = (await client.get(_col_url(col_id, "/list"))).json()
        assert body["limit"] == 100
        assert body["offset"] == 0


# ─────────────────────────── Get ─────────────────────────────


class TestGetDocument:
    """GET /api/v1/collections/{collection_id}/documents/{document_id}"""

    @pytest.mark.asyncio
    async def test_get_returns_200_with_filename(self, client: httpx.AsyncClient) -> None:
        """200 is returned and filename matches."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = make_document_orm(id=doc_id, collection_id=col_id, filename="report.pdf")
        CONTEXT.document_repo.get_by_id.return_value = doc
        response = await client.get(_doc_url(col_id, doc_id))
        assert response.status_code == 200
        assert response.json()["filename"] == "report.pdf"

    @pytest.mark.asyncio
    async def test_get_returns_404_for_unknown_document(
        self, client: httpx.AsyncClient
    ) -> None:
        """404 when the document does not exist."""
        CONTEXT.document_repo.get_by_id.return_value = None
        response = await client.get(_doc_url(uuid.uuid4(), uuid.uuid4()))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_returns_404_when_collection_mismatch(
        self, client: httpx.AsyncClient
    ) -> None:
        """404 when the document belongs to a different collection."""
        col_id = uuid.uuid4()
        doc = make_document_orm(collection_id=uuid.uuid4())  # different collection
        CONTEXT.document_repo.get_by_id.return_value = doc
        response = await client.get(_doc_url(col_id, uuid.uuid4()))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_response_has_aggregated_fields(
        self, client: httpx.AsyncClient
    ) -> None:
        """Response includes chunk_count, block_count, has_original, has_pdf, has_markdown."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = make_document_orm(id=doc_id, collection_id=col_id)
        CONTEXT.document_repo.get_by_id.return_value = doc
        CONTEXT.chunk_repo.count_by_document.return_value = 5
        CONTEXT.document_repo.count_blocks.return_value = 10
        CONTEXT.document_repo.get_stage_run_summary.return_value = {"s1": "done", "s6": "done"}
        body = (await client.get(_doc_url(col_id, doc_id))).json()
        assert body["chunk_count"] == 5
        assert "has_original" in body
        assert "indexed" in body


# ─────────────────────────── Update ─────────────────────────────


class TestUpdateDocument:
    """POST /api/v1/collections/{collection_id}/documents/{document_id}/update"""

    @pytest.mark.asyncio
    async def test_update_returns_200_on_success(self, client: httpx.AsyncClient) -> None:
        """Metadata patch applied successfully → 200."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = make_document_orm(id=doc_id, collection_id=col_id, user_meta={})
        col = make_collection_orm(id=col_id, unknown_field_policy="ignore")
        CONTEXT.document_repo.get_by_id.return_value = doc
        CONTEXT.collection_repo.get_by_id.return_value = col
        response = await client.post(
            _doc_url(col_id, doc_id, "/update"),
            json={"metadata": {"tag": "report"}},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_returns_404_for_unknown_document(
        self, client: httpx.AsyncClient
    ) -> None:
        """404 when document does not exist or belongs to a different collection."""
        CONTEXT.document_repo.get_by_id.return_value = None
        response = await client.post(
            _doc_url(uuid.uuid4(), uuid.uuid4(), "/update"),
            json={"metadata": {}},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_response_has_changed_fields(
        self, client: httpx.AsyncClient
    ) -> None:
        """Response includes user_meta, changed_fields, reindexed."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = make_document_orm(id=doc_id, collection_id=col_id, user_meta={})
        col = make_collection_orm(id=col_id, unknown_field_policy="ignore")
        CONTEXT.document_repo.get_by_id.return_value = doc
        CONTEXT.collection_repo.get_by_id.return_value = col
        body = (
            await client.post(
                _doc_url(col_id, doc_id, "/update"),
                json={"metadata": {"author": "Alice"}},
            )
        ).json()
        assert "changed_fields" in body
        assert "reindexed" in body
        assert "user_meta" in body

    @pytest.mark.asyncio
    async def test_update_reindex_false_sets_reindexed_false(
        self, client: httpx.AsyncClient
    ) -> None:
        """reindex=False (default) leaves reindexed=False in response."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = make_document_orm(id=doc_id, collection_id=col_id, user_meta={})
        col = make_collection_orm(id=col_id, unknown_field_policy="ignore")
        CONTEXT.document_repo.get_by_id.return_value = doc
        CONTEXT.collection_repo.get_by_id.return_value = col
        body = (
            await client.post(
                _doc_url(col_id, doc_id, "/update"),
                json={"metadata": {"k": "v"}, "reindex": False},
            )
        ).json()
        assert body["reindexed"] is False

    @pytest.mark.asyncio
    async def test_update_unknown_field_rejected_returns_422(
        self, client: httpx.AsyncClient
    ) -> None:
        """Unknown metadata field rejected by schema with unknown_field_policy=reject → 422."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = make_document_orm(id=doc_id, collection_id=col_id, user_meta={})
        col = make_collection_orm(id=col_id, unknown_field_policy="reject", metadata_fields=[])
        CONTEXT.document_repo.get_by_id.return_value = doc
        CONTEXT.collection_repo.get_by_id.return_value = col
        response = await client.post(
            _doc_url(col_id, doc_id, "/update"),
            json={"metadata": {"unregistered_field": "value"}},
        )
        assert response.status_code == 422


# ─────────────────────────── Reingest ─────────────────────────────


class TestReingestDocument:
    """POST /api/v1/collections/{collection_id}/documents/{document_id}/reingest"""

    @pytest.mark.asyncio
    async def test_reingest_returns_202(self, client: httpx.AsyncClient) -> None:
        """Re-enqueuing a document returns 202."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        job_id = uuid.uuid4()
        job = MagicMock()
        job.id = job_id
        doc = make_document_orm(id=doc_id, collection_id=col_id)
        CONTEXT.document_repo.get_by_id.return_value = doc
        CONTEXT.job_repo.create.return_value = job
        response = await client.post(
            _doc_url(col_id, doc_id, "/reingest"), json={}
        )
        assert response.status_code == 202

    @pytest.mark.asyncio
    async def test_reingest_returns_404_for_unknown_document(
        self, client: httpx.AsyncClient
    ) -> None:
        """404 when the document does not exist."""
        CONTEXT.document_repo.get_by_id.return_value = None
        response = await client.post(
            _doc_url(uuid.uuid4(), uuid.uuid4(), "/reingest"), json={}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_reingest_response_has_document_id_job_id_status(
        self, client: httpx.AsyncClient
    ) -> None:
        """Response contains document_id, job_id, and status='pending'."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        job_id = uuid.uuid4()
        job = MagicMock()
        job.id = job_id
        doc = make_document_orm(id=doc_id, collection_id=col_id)
        CONTEXT.document_repo.get_by_id.return_value = doc
        CONTEXT.job_repo.create.return_value = job
        body = (
            await client.post(_doc_url(col_id, doc_id, "/reingest"), json={})
        ).json()
        assert body["status"] == "pending"
        assert "document_id" in body
        assert "job_id" in body

    @pytest.mark.asyncio
    async def test_reingest_force_true_invalidates_cache(
        self, client: httpx.AsyncClient
    ) -> None:
        """force=True triggers node_cache.invalidate_document."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        job = MagicMock()
        job.id = uuid.uuid4()
        doc = make_document_orm(id=doc_id, collection_id=col_id)
        CONTEXT.document_repo.get_by_id.return_value = doc
        CONTEXT.job_repo.create.return_value = job
        await client.post(_doc_url(col_id, doc_id, "/reingest"), json={"force": True})
        CONTEXT.node_cache.invalidate_document.assert_called_once()


# ─────────────────────────── Delete ─────────────────────────────


class TestDeleteDocument:
    """DELETE /api/v1/collections/{collection_id}/documents/{document_id}/delete"""

    @pytest.mark.asyncio
    async def test_delete_returns_200(self, client: httpx.AsyncClient) -> None:
        """Deleting a known document returns 200."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = make_document_orm(id=doc_id, collection_id=col_id)
        CONTEXT.document_repo.get_by_id.return_value = doc
        response = await client.delete(_doc_url(col_id, doc_id, "/delete"))
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_returns_404_for_unknown_document(
        self, client: httpx.AsyncClient
    ) -> None:
        """404 when the document does not exist."""
        CONTEXT.document_repo.get_by_id.return_value = None
        response = await client.delete(_doc_url(uuid.uuid4(), uuid.uuid4(), "/delete"))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_response_shape(self, client: httpx.AsyncClient) -> None:
        """Response has deleted, id, qdrant_points_deleted, blob_deleted."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = make_document_orm(id=doc_id, collection_id=col_id)
        CONTEXT.document_repo.get_by_id.return_value = doc
        body = (await client.delete(_doc_url(col_id, doc_id, "/delete"))).json()
        assert body["deleted"] is True
        assert "id" in body
        assert "qdrant_points_deleted" in body
        assert "blob_deleted" in body

    @pytest.mark.asyncio
    async def test_delete_blob_deleted_true_when_hash_not_shared(
        self, client: httpx.AsyncClient
    ) -> None:
        """Blob is deleted when the source_hash is not shared by another document."""
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = make_document_orm(id=doc_id, collection_id=col_id, source_hash="unique_hash")
        CONTEXT.document_repo.get_by_id.return_value = doc
        CONTEXT.document_repo.is_source_hash_used_by_other_documents.return_value = False
        body = (await client.delete(_doc_url(col_id, doc_id, "/delete"))).json()
        assert body["blob_deleted"] is True
