# ====== Code Summary ======
# Tests for the collection config section: state / schema / history / update / rollback.
# All endpoints live under /api/v1/collections/{collection_id}/config/*.

import uuid
from unittest.mock import AsyncMock, MagicMock
import datetime

import httpx
import pytest

from backend.context import CONTEXT
from tests.units.api.conftest import make_collection_orm


def _col_id():
    return uuid.uuid4()


def _url(collection_id: uuid.UUID, suffix: str) -> str:
    return f"/api/v1/collections/{collection_id}/config/{suffix}"


class TestGetConfigState:
    """GET /api/v1/collections/{collection_id}/config/state"""

    @pytest.mark.asyncio
    async def test_state_returns_200_for_known_collection(
        self, client: httpx.AsyncClient
    ) -> None:
        """200 is returned for an existing collection."""
        col_id = _col_id()
        col = make_collection_orm(id=col_id)
        CONTEXT.collection_repo.get_by_id.return_value = col
        response = await client.get(_url(col_id, "state"))
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_state_returns_404_for_unknown_collection(
        self, client: httpx.AsyncClient
    ) -> None:
        """404 when the collection does not exist."""
        CONTEXT.collection_repo.get_by_id.return_value = None
        response = await client.get(_url(_col_id(), "state"))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_state_response_has_required_fields(
        self, client: httpx.AsyncClient
    ) -> None:
        """Response exposes id, name, pipeline_version, needs_reindex, pipeline, metadata_fields."""
        col_id = _col_id()
        col = make_collection_orm(id=col_id, name="Test Col")
        CONTEXT.collection_repo.get_by_id.return_value = col
        body = (await client.get(_url(col_id, "state"))).json()
        for field in (
            "id", "name", "pipeline_version", "needs_reindex",
            "supported_formats", "pipeline", "metadata_fields",
        ):
            assert field in body, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_state_id_matches_collection(self, client: httpx.AsyncClient) -> None:
        """The id in the response matches the requested collection_id."""
        col_id = _col_id()
        col = make_collection_orm(id=col_id)
        CONTEXT.collection_repo.get_by_id.return_value = col
        body = (await client.get(_url(col_id, "state"))).json()
        assert body["id"] == str(col_id)

    @pytest.mark.asyncio
    async def test_state_pipeline_is_redacted_dict(
        self, client: httpx.AsyncClient
    ) -> None:
        """Pipeline is returned as a dict (credentials redacted)."""
        col_id = _col_id()
        col = make_collection_orm(id=col_id)
        CONTEXT.collection_repo.get_by_id.return_value = col
        body = (await client.get(_url(col_id, "state"))).json()
        assert isinstance(body["pipeline"], dict)


class TestGetConfigSchema:
    """GET /api/v1/collections/{collection_id}/config/schema"""

    @pytest.mark.asyncio
    async def test_schema_returns_200_for_known_collection(
        self, client: httpx.AsyncClient
    ) -> None:
        """200 when the collection exists."""
        col_id = _col_id()
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(id=col_id)
        response = await client.get(_url(col_id, "schema"))
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_schema_returns_404_for_unknown_collection(
        self, client: httpx.AsyncClient
    ) -> None:
        """404 when the collection does not exist."""
        CONTEXT.collection_repo.get_by_id.return_value = None
        response = await client.get(_url(_col_id(), "schema"))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_schema_response_has_metadata_fields(
        self, client: httpx.AsyncClient
    ) -> None:
        """Response contains the collection's metadata_fields (system + custom)."""
        col_id = _col_id()
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(id=col_id)
        body = (await client.get(_url(col_id, "schema"))).json()
        assert "metadata_fields" in body
        assert "stages" not in body

    @pytest.mark.asyncio
    async def test_schema_fields_include_system_entries(
        self, client: httpx.AsyncClient
    ) -> None:
        """System metadata fields are present in the schema (is_system=True)."""
        col_id = _col_id()
        sys_field = {
            "field_name": "filename", "field_type": "string",
            "required": False, "filterable": True, "lexical": True, "semantic": False,
            "enum_values": None, "is_system": True,
        }
        col = make_collection_orm(id=col_id, metadata_fields=[sys_field])
        CONTEXT.collection_repo.get_by_id.return_value = col
        body = (await client.get(_url(col_id, "schema"))).json()
        system_fields = [f for f in body["metadata_fields"] if f.get("is_system")]
        assert len(system_fields) > 0


class TestGetConfigHistory:
    """GET /api/v1/collections/{collection_id}/config/history"""

    @pytest.mark.asyncio
    async def test_history_returns_404_for_unknown_collection(
        self, client: httpx.AsyncClient
    ) -> None:
        """404 when the collection does not exist."""
        CONTEXT.collection_repo.get_by_id.return_value = None
        response = await client.get(_url(_col_id(), "history"))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_history_empty_returns_200(self, client: httpx.AsyncClient) -> None:
        """Collection with no history returns 200 with an empty versions list."""
        col_id = _col_id()
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(id=col_id)
        CONTEXT.config_repo.list_versions.return_value = []
        body = (await client.get(_url(col_id, "history"))).json()
        assert body["total"] == 0
        assert body["versions"] == []

    @pytest.mark.asyncio
    async def test_history_returns_version_summaries(
        self, client: httpx.AsyncClient
    ) -> None:
        """Each version in the list has the expected fields."""
        col_id = _col_id()
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(id=col_id)
        v = MagicMock()
        v.version = 1
        v.pipeline_version = "v1"
        v.note = "initial"
        v.created_at = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
        CONTEXT.config_repo.list_versions.return_value = [v]
        body = (await client.get(_url(col_id, "history"))).json()
        assert body["total"] == 1
        assert body["versions"][0]["version"] == 1

    @pytest.mark.asyncio
    async def test_history_collection_id_in_response(
        self, client: httpx.AsyncClient
    ) -> None:
        """Response includes the collection_id."""
        col_id = _col_id()
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(id=col_id)
        CONTEXT.config_repo.list_versions.return_value = []
        body = (await client.get(_url(col_id, "history"))).json()
        assert body["collection_id"] == str(col_id)


class TestUpdateConfig:
    """POST /api/v1/collections/{collection_id}/config/update"""

    @pytest.mark.asyncio
    async def test_update_returns_404_for_unknown_collection(
        self, client: httpx.AsyncClient
    ) -> None:
        """404 when the collection does not exist."""
        CONTEXT.collection_repo.get_by_id.return_value = None
        response = await client.post(
            _url(_col_id(), "update"), json={"patch": {}}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_returns_200_on_success(self, client: httpx.AsyncClient) -> None:
        """Valid patch returns 200 with the new config state."""
        col_id = _col_id()
        col = make_collection_orm(id=col_id)
        updated_col = make_collection_orm(id=col_id, name="Updated")
        CONTEXT.collection_repo.get_by_id.return_value = col
        CONTEXT.config_repo.apply_config.return_value = updated_col
        response = await client.post(
            _url(col_id, "update"), json={"patch": {}, "note": "bump"}
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_response_is_config_state(self, client: httpx.AsyncClient) -> None:
        """Response body is a ConfigStateResponse with required fields."""
        col_id = _col_id()
        col = make_collection_orm(id=col_id)
        CONTEXT.collection_repo.get_by_id.return_value = col
        CONTEXT.config_repo.apply_config.return_value = make_collection_orm(id=col_id)
        body = (
            await client.post(_url(col_id, "update"), json={"patch": {}})
        ).json()
        assert "id" in body
        assert "pipeline_version" in body

    @pytest.mark.asyncio
    async def test_update_empty_patch_is_valid(self, client: httpx.AsyncClient) -> None:
        """An empty patch dict is accepted (no change, still valid)."""
        col_id = _col_id()
        col = make_collection_orm(id=col_id)
        CONTEXT.collection_repo.get_by_id.return_value = col
        CONTEXT.config_repo.apply_config.return_value = make_collection_orm(id=col_id)
        response = await client.post(_url(col_id, "update"), json={"patch": {}})
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_invalid_config_returns_422(
        self, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A config that the coherence validator flags as error-severity → 422 (not applied)."""
        from libs.config.validation import ConfigValidator
        col_id = _col_id()
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(id=col_id)
        # Override the conftest stub (which returns []) so the validator reports an error issue.
        monkeypatch.setattr(
            ConfigValidator, "validate",
            lambda *a, **kw: [{"severity": "error", "code": "bad_pipeline",
                               "field": "pipeline", "message": "Unknown provider id."}],
        )
        # A benign patch (so resolve_pipeline succeeds); the monkeypatched validator is what rejects.
        response = await client.post(
            _url(col_id, "update"), json={"patch": {"embedding_model": "BAAI/bge-m3-alt"}}
        )
        assert response.status_code == 422
        # apply_config must NOT run when validation fails (no mutation on a rejected config).
        CONTEXT.config_repo.apply_config.assert_not_called()


class TestRollbackConfig:
    """POST /api/v1/collections/{collection_id}/config/rollback"""

    @pytest.mark.asyncio
    async def test_rollback_returns_404_for_unknown_collection(
        self, client: httpx.AsyncClient
    ) -> None:
        """404 when the collection does not exist."""
        CONTEXT.collection_repo.get_by_id.return_value = None
        response = await client.post(_url(_col_id(), "rollback"), json={"version": 1})
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_rollback_returns_404_for_unknown_version(
        self, client: httpx.AsyncClient
    ) -> None:
        """404 when the requested version number doesn't exist."""
        col_id = _col_id()
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(id=col_id)
        CONTEXT.config_repo.get_version.return_value = None
        response = await client.post(_url(col_id, "rollback"), json={"version": 99})
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_rollback_returns_200_on_success(self, client: httpx.AsyncClient) -> None:
        """Known version successfully rolled back → 200."""
        col_id = _col_id()
        col = make_collection_orm(id=col_id)
        CONTEXT.collection_repo.get_by_id.return_value = col
        snapshot = MagicMock()
        snapshot.config = {
            "supported_formats": ["pdf"],
            "max_file_size_bytes": 10_000_000,
            "locality_policy": "external_allowed",
            "embedding_model": "BAAI/bge-m3",
            "unknown_field_policy": "ignore",
            "pipeline": {},
            "metadata_fields": [],
        }
        CONTEXT.config_repo.get_version.return_value = snapshot
        CONTEXT.config_repo.apply_config.return_value = make_collection_orm(id=col_id)
        response = await client.post(_url(col_id, "rollback"), json={"version": 1})
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_rollback_version_must_be_positive(
        self, client: httpx.AsyncClient
    ) -> None:
        """version < 1 violates ge=1 constraint → 422."""
        col_id = _col_id()
        response = await client.post(_url(col_id, "rollback"), json={"version": 0})
        assert response.status_code == 422
