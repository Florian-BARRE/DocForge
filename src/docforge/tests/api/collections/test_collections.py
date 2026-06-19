# ====== Code Summary ======
# Tests for the collections section: list / create / delete.

import uuid
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.exc import IntegrityError

import httpx
import pytest

from backend.context import CONTEXT
from tests.api.conftest import make_collection_orm


_CREATE_BODY = {
    "name": "My Collection",
    "supported_formats": ["pdf"],
    "max_file_size_bytes": 10_000_000,
    "locality_policy": "external_allowed",
    "embedding_model": "BAAI/bge-m3",
    "unknown_field_policy": "ignore",
    "pipeline": {},
}


class TestListCollections:
    """GET /api/v1/collections/list"""

    @pytest.mark.asyncio
    async def test_list_empty_returns_200(self, client: httpx.AsyncClient) -> None:
        """Empty table returns 200 with an empty list and total=0."""
        CONTEXT.collection_repo.list_all.return_value = []
        response = await client.get("/api/v1/collections/list")
        assert response.status_code == 200
        body = response.json()
        assert body["collections"] == []
        assert body["total"] == 0

    @pytest.mark.asyncio
    async def test_list_returns_all_collections(self, client: httpx.AsyncClient) -> None:
        """All persisted collections appear in the response."""
        cols = [make_collection_orm(name=f"Col {i}") for i in range(3)]
        CONTEXT.collection_repo.list_all.return_value = cols
        response = await client.get("/api/v1/collections/list")
        body = response.json()
        assert body["total"] == 3
        assert len(body["collections"]) == 3

    @pytest.mark.asyncio
    async def test_list_response_has_required_fields(self, client: httpx.AsyncClient) -> None:
        """Each collection entry exposes id, name, pipeline_version, created_at."""
        col = make_collection_orm(name="Alpha")
        CONTEXT.collection_repo.list_all.return_value = [col]
        response = await client.get("/api/v1/collections/list")
        entry = response.json()["collections"][0]
        for field in ("id", "name", "pipeline_version", "created_at"):
            assert field in entry, f"Missing field: {field}"


class TestCreateCollection:
    """POST /api/v1/collections/create"""

    @pytest.mark.asyncio
    async def test_create_returns_201(self, client: httpx.AsyncClient) -> None:
        """Successful create returns HTTP 201."""
        col = make_collection_orm(name="My Collection")
        CONTEXT.collection_repo.create.return_value = col
        response = await client.post("/api/v1/collections/create", json=_CREATE_BODY)
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_response_has_id_and_name(self, client: httpx.AsyncClient) -> None:
        """Response body must include id and the requested name."""
        col = make_collection_orm(name="My Collection")
        CONTEXT.collection_repo.create.return_value = col
        response = await client.post("/api/v1/collections/create", json=_CREATE_BODY)
        body = response.json()
        assert "id" in body
        assert body["name"] == "My Collection"

    @pytest.mark.asyncio
    async def test_create_resolves_pipeline_defaults_and_returns_applied(self, client: httpx.AsyncClient) -> None:
        """Omitted pipeline is resolved to full defaults and echoed; `applied` documents it."""
        CONTEXT.collection_repo.create.return_value = make_collection_orm(name="My Collection", pipeline={})
        response = await client.post("/api/v1/collections/create", json=_CREATE_BODY)
        assert response.status_code == 201
        body = response.json()
        # Resolved pipeline echoed (defaults filled, not the empty {} sent)
        assert body["pipeline"]["chunk"]["split_method"]["id"] == "token_budget"
        assert body["pipeline"]["embed"]["chain"][0]["id"] == "tei"
        # Transparency envelope present and coherent
        applied = body["applied"]
        assert applied is not None
        assert applied["pipeline"]["chunk"] == "default"   # caller sent pipeline={}
        assert "metadata_fields" not in applied["provided"]  # schema not sent
        assert "created_at" in body

    @pytest.mark.asyncio
    async def test_create_marks_provided_pipeline_section(self, client: httpx.AsyncClient) -> None:
        """A pipeline section sent by the caller is reported as 'provided', others as 'default'."""
        CONTEXT.collection_repo.create.return_value = make_collection_orm(name="My Collection")
        body_in = {**_CREATE_BODY, "pipeline": {"chunk": {"split_method": {"id": "sentence_window"}}}}
        response = await client.post("/api/v1/collections/create", json=body_in)
        assert response.status_code == 201
        applied = response.json()["applied"]
        assert applied["pipeline"]["chunk"] == "provided"
        assert applied["pipeline"]["parse"] == "default"

    @pytest.mark.asyncio
    async def test_create_duplicate_name_returns_409(self, client: httpx.AsyncClient) -> None:
        """Duplicate collection name raises IntegrityError → 409."""
        CONTEXT.collection_repo.create.side_effect = IntegrityError("", "", Exception())
        response = await client.post("/api/v1/collections/create", json=_CREATE_BODY)
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_create_missing_name_returns_422(self, client: httpx.AsyncClient) -> None:
        """Body without 'name' fails Pydantic validation → 422."""
        response = await client.post("/api/v1/collections/create", json={})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_empty_name_returns_422(self, client: httpx.AsyncClient) -> None:
        """Empty-string name violates min_length=1 → 422."""
        body = {**_CREATE_BODY, "name": ""}
        response = await client.post("/api/v1/collections/create", json=body)
        assert response.status_code == 422


class TestDeleteCollection:
    """DELETE /api/v1/collections/{collection_id}/delete"""

    @pytest.mark.asyncio
    async def test_delete_existing_returns_200(self, client: httpx.AsyncClient) -> None:
        """Deleting a known collection returns 200."""
        col_id = uuid.uuid4()
        col = make_collection_orm(id=col_id)
        CONTEXT.collection_repo.get_by_id.return_value = col
        CONTEXT.document_repo.list_source_hashes.return_value = []
        response = await client.delete(f"/api/v1/collections/{col_id}/delete")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_missing_collection_returns_404(self, client: httpx.AsyncClient) -> None:
        """Unknown collection_id → 404."""
        CONTEXT.collection_repo.get_by_id.return_value = None
        response = await client.delete(f"/api/v1/collections/{uuid.uuid4()}/delete")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_response_deleted_true(self, client: httpx.AsyncClient) -> None:
        """Response body confirms deleted=True."""
        col_id = uuid.uuid4()
        col = make_collection_orm(id=col_id)
        CONTEXT.collection_repo.get_by_id.return_value = col
        CONTEXT.document_repo.list_source_hashes.return_value = []
        response = await client.delete(f"/api/v1/collections/{col_id}/delete")
        body = response.json()
        assert body["deleted"] is True

    @pytest.mark.asyncio
    async def test_delete_response_id_matches(self, client: httpx.AsyncClient) -> None:
        """Response id matches the deleted collection_id."""
        col_id = uuid.uuid4()
        col = make_collection_orm(id=col_id)
        CONTEXT.collection_repo.get_by_id.return_value = col
        CONTEXT.document_repo.list_source_hashes.return_value = []
        response = await client.delete(f"/api/v1/collections/{col_id}/delete")
        assert response.json()["id"] == str(col_id)

    @pytest.mark.asyncio
    async def test_delete_skips_shared_blobs(self, client: httpx.AsyncClient) -> None:
        """S3 blobs shared by another collection are not deleted."""
        col_id = uuid.uuid4()
        col = make_collection_orm(id=col_id)
        CONTEXT.collection_repo.get_by_id.return_value = col
        # One source_hash exists but is shared → is_source_hash_shared=True
        CONTEXT.document_repo.list_source_hashes.return_value = ["sha256abc"]
        CONTEXT.document_repo.is_source_hash_shared.return_value = True
        response = await client.delete(f"/api/v1/collections/{col_id}/delete")
        assert response.status_code == 200
        # s3.delete should NOT have been called
        CONTEXT.s3.delete.assert_not_called()
