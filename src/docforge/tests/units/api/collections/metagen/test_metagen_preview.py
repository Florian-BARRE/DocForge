# ====== Code Summary ======
# Tests for POST /api/v1/collections/{collection_id}/metagen/preview.
# Covers: model_validator (exactly one of chunk_id/sample_text), 422 when the preview
# service raises MetagenPreviewError (no target / not generated / no provider), 404 for
# unknown collection, the happy path (all response fields asserted), and the CONFIG_WRITE
# capability gate (403 on auth-on scoped key without config.write).

# ====== Standard Library Imports ======
import uuid
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

# ====== Third-Party Library Imports ======
import httpx
import pytest
import pytest_asyncio

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.auth.models import Principal
from backend.libs.metagen.preview import MetagenPreviewError, MetagenPreviewResult
from common_libs.storage.postgres.models import UserRole
from tests.units.api.conftest import make_collection_orm


# ─── Helpers ────────────────────────────────────────────────────────────────────

def _url(collection_id: uuid.UUID) -> str:
    """Build the preview endpoint URL for a given collection."""
    return f"/api/v1/collections/{collection_id}/metagen/preview"


def _body(**overrides) -> dict:
    """Build a minimal valid preview request body (sample_text variant)."""
    base = {
        "field_name": "kw",
        "sample_text": "Python is a general-purpose programming language.",
    }
    base.update(overrides)
    return base


def _ok_result(**overrides) -> MetagenPreviewResult:
    """Return a stubbed MetagenPreviewResult for the happy path, with per-test overrides."""
    defaults = dict(
        value=["python", "programming"],
        raw={"kw": ["python", "programming"]},
        token_estimate=200,
        cost_estimate=0.0003,
        scope="chunk",
        provider="openai_compat",
        degraded=False,
    )
    defaults.update(overrides)
    return MetagenPreviewResult(**defaults)


_ROOT_USER_ID = uuid.uuid4()
_ROOT_API_KEY = "preview-test-root-key"
_ROOT_HEADERS = {"Authorization": f"Bearer {_ROOT_API_KEY}"}
_ROOT_PRINCIPAL = Principal(
    user_id=_ROOT_USER_ID,
    username="root",
    global_role=UserRole.ROOT,
    is_root=True,
    permissions=None,  # None = full access
)


def _scoped_principal(*, permissions: dict | None) -> Principal:
    """Return a scoped API-key principal with given permissions scope."""
    return Principal(
        user_id=_ROOT_USER_ID,
        username="root",
        global_role=UserRole.ROOT,
        is_root=True,
        permissions=permissions,
    )


# ─── Auth-on fixture (mirrors test_auth_api.py pattern) ─────────────────────────

@pytest_asyncio.fixture
async def authed_client(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[httpx.AsyncClient]:
    """Enable AUTH_ENABLED=True and wire root key → root principal for auth gate tests."""
    monkeypatch.setattr(CONTEXT.RUNTIME_CONFIG, "AUTH_ENABLED", True, raising=False)

    async def _resolve(bearer: str | None) -> Principal | None:
        return _ROOT_PRINCIPAL if bearer == _ROOT_API_KEY else None

    CONTEXT.auth_service.resolve_principal = AsyncMock(side_effect=_resolve)
    yield client


# ─── Model validator (both/neither source) ────────────────────────────────────

class TestModelValidator:
    """The request validator requires exactly one of chunk_id / sample_text."""

    @pytest.mark.asyncio
    async def test_neither_chunk_id_nor_sample_text_is_422(
        self, client: httpx.AsyncClient
    ) -> None:
        """Providing neither chunk_id nor sample_text → 422 (Pydantic model_validator)."""
        col_id = uuid.uuid4()
        col = make_collection_orm(id=col_id)
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=col)
        response = await client.post(
            _url(col_id), json={"field_name": "kw"}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_both_chunk_id_and_sample_text_is_422(
        self, client: httpx.AsyncClient
    ) -> None:
        """Providing both chunk_id and sample_text → 422."""
        col_id = uuid.uuid4()
        col = make_collection_orm(id=col_id)
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=col)
        response = await client.post(
            _url(col_id),
            json={
                "field_name": "kw",
                "chunk_id": str(uuid.uuid4()),
                "sample_text": "some text",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_sample_text_only_is_valid(self, client: httpx.AsyncClient) -> None:
        """sample_text alone passes model_validator (body shape is correct)."""
        col_id = uuid.uuid4()
        col = make_collection_orm(id=col_id)
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=col)
        with patch(
            "backend.routers.collections.metagen.router.MetagenPreviewService.preview",
            new_callable=AsyncMock,
            return_value=_ok_result(),
        ):
            response = await client.post(_url(col_id), json=_body())
        # 200 means the model validator passed; exact body is tested in TestHappyPath
        assert response.status_code == 200


# ─── 404 — unknown collection ─────────────────────────────────────────────────

class TestCollectionNotFound:
    """The collection lookup returns 404 when the collection does not exist."""

    @pytest.mark.asyncio
    async def test_unknown_collection_returns_404(self, client: httpx.AsyncClient) -> None:
        """404 when collection_repo.get_by_id returns None."""
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=None)
        response = await client.post(_url(uuid.uuid4()), json=_body())
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_404_detail_mentions_collection(self, client: httpx.AsyncClient) -> None:
        """The 404 detail message contains the collection ID."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=None)
        response = await client.post(_url(col_id), json=_body())
        assert str(col_id) in response.json()["detail"]


# ─── 422 — MetagenPreviewError paths ─────────────────────────────────────────

class TestPreviewErrors:
    """422 is returned when MetagenPreviewService.preview raises MetagenPreviewError."""

    @pytest.mark.asyncio
    async def test_no_target_raises_422(self, client: httpx.AsyncClient) -> None:
        """No metagen target bound to the field → 422."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=make_collection_orm(id=col_id))
        with patch(
            "backend.routers.collections.metagen.router.MetagenPreviewService.preview",
            new_callable=AsyncMock,
            side_effect=MetagenPreviewError("No metagen target binds field 'kw'."),
        ):
            response = await client.post(_url(col_id), json=_body())
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_no_target_detail_is_error_string(self, client: httpx.AsyncClient) -> None:
        """The 422 detail string carries the MetagenPreviewError message."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=make_collection_orm(id=col_id))
        err_msg = "No metagen target binds field 'kw'."
        with patch(
            "backend.routers.collections.metagen.router.MetagenPreviewService.preview",
            new_callable=AsyncMock,
            side_effect=MetagenPreviewError(err_msg),
        ):
            response = await client.post(_url(col_id), json=_body())
        assert err_msg in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_field_not_generated_raises_422(self, client: httpx.AsyncClient) -> None:
        """Field is not origin='generated' → 422 (MetagenPreviewError from preview service)."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=make_collection_orm(id=col_id))
        with patch(
            "backend.routers.collections.metagen.router.MetagenPreviewService.preview",
            new_callable=AsyncMock,
            side_effect=MetagenPreviewError("Field 'kw' is not a metadata field with origin='generated'."),
        ):
            response = await client.post(_url(col_id), json=_body())
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_no_provider_raises_422(self, client: httpx.AsyncClient) -> None:
        """No LLM chain configured → 422 (MetagenPreviewError from _build_chain)."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=make_collection_orm(id=col_id))
        with patch(
            "backend.routers.collections.metagen.router.MetagenPreviewService.preview",
            new_callable=AsyncMock,
            side_effect=MetagenPreviewError(
                "No LLM provider configured for metagen — add one to the metagen chain."
            ),
        ):
            response = await client.post(_url(col_id), json=_body())
        assert response.status_code == 422


# ─── Happy path ───────────────────────────────────────────────────────────────

class TestHappyPath:
    """A well-formed request returns 200 with all MetagenPreviewResponse fields."""

    @pytest.mark.asyncio
    async def test_happy_path_returns_200(self, client: httpx.AsyncClient) -> None:
        """Valid request → 200."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=make_collection_orm(id=col_id))
        with patch(
            "backend.routers.collections.metagen.router.MetagenPreviewService.preview",
            new_callable=AsyncMock,
            return_value=_ok_result(),
        ):
            response = await client.post(_url(col_id), json=_body())
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_happy_path_response_has_all_fields(self, client: httpx.AsyncClient) -> None:
        """The response body carries all declared MetagenPreviewResponse fields."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=make_collection_orm(id=col_id))
        with patch(
            "backend.routers.collections.metagen.router.MetagenPreviewService.preview",
            new_callable=AsyncMock,
            return_value=_ok_result(),
        ):
            body = (await client.post(_url(col_id), json=_body())).json()
        for key in ("field_name", "scope", "value", "raw", "token_estimate", "cost_estimate",
                    "provider", "degraded"):
            assert key in body, f"Missing field: {key}"

    @pytest.mark.asyncio
    async def test_happy_path_response_values(self, client: httpx.AsyncClient) -> None:
        """Response values mirror what the preview service returned."""
        col_id = uuid.uuid4()
        result = _ok_result(
            value=["python", "programming"],
            raw={"kw": ["python", "programming"]},
            token_estimate=200,
            cost_estimate=0.0003,
            scope="chunk",
            provider="openai_compat",
            degraded=False,
        )
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=make_collection_orm(id=col_id))
        with patch(
            "backend.routers.collections.metagen.router.MetagenPreviewService.preview",
            new_callable=AsyncMock,
            return_value=result,
        ):
            body = (await client.post(_url(col_id), json=_body())).json()
        assert body["field_name"] == "kw"
        assert body["scope"] == "chunk"
        assert body["value"] == ["python", "programming"]
        assert body["raw"] == {"kw": ["python", "programming"]}
        assert body["token_estimate"] == 200
        assert body["cost_estimate"] == pytest.approx(0.0003, abs=1e-6)
        assert body["provider"] == "openai_compat"
        assert body["degraded"] is False

    @pytest.mark.asyncio
    async def test_degraded_chain_returns_200_not_500(self, client: httpx.AsyncClient) -> None:
        """A degraded result (chain exhausted) is still a successful 200, not an error."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=make_collection_orm(id=col_id))
        with patch(
            "backend.routers.collections.metagen.router.MetagenPreviewService.preview",
            new_callable=AsyncMock,
            return_value=_ok_result(value=None, degraded=True, provider=None),
        ):
            response = await client.post(_url(col_id), json=_body())
        assert response.status_code == 200
        body = response.json()
        assert body["degraded"] is True
        assert body["value"] is None
        assert body["provider"] is None

    @pytest.mark.asyncio
    async def test_document_scope_preview(self, client: httpx.AsyncClient) -> None:
        """scope='document' is surfaced correctly in the response."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=make_collection_orm(id=col_id))
        with patch(
            "backend.routers.collections.metagen.router.MetagenPreviewService.preview",
            new_callable=AsyncMock,
            return_value=_ok_result(scope="document"),
        ):
            body = (await client.post(_url(col_id), json=_body())).json()
        assert body["scope"] == "document"


# ─── Chunk content source ─────────────────────────────────────────────────────

class TestChunkContentSource:
    """chunk_id content path: 404 when chunk not found or in a different collection."""

    @pytest.mark.asyncio
    async def test_unknown_chunk_returns_404(self, client: httpx.AsyncClient) -> None:
        """A chunk_id that does not exist → 404."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=make_collection_orm(id=col_id))
        CONTEXT.chunk_repo.get_by_id = AsyncMock(return_value=None)
        response = await client.post(
            _url(col_id),
            json={"field_name": "kw", "chunk_id": str(uuid.uuid4())},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_chunk_in_other_collection_returns_404(
        self, client: httpx.AsyncClient
    ) -> None:
        """A chunk belonging to a different collection → 404 (scope mismatch)."""
        col_id = uuid.uuid4()
        other_col_id = uuid.uuid4()  # the chunk's document belongs here
        chunk_id = uuid.uuid4()
        doc = MagicMock()
        doc.collection_id = other_col_id  # != col_id

        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=make_collection_orm(id=col_id))
        CONTEXT.chunk_repo.get_by_id = AsyncMock(
            return_value={"document_id": str(uuid.uuid4()), "raw_text": "some text", "prov": {}}
        )
        CONTEXT.document_repo.get_by_id = AsyncMock(return_value=doc)
        response = await client.post(
            _url(col_id),
            json={"field_name": "kw", "chunk_id": str(chunk_id)},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_valid_chunk_returns_200(self, client: httpx.AsyncClient) -> None:
        """A chunk that belongs to this collection → 200 (preview service called)."""
        col_id = uuid.uuid4()
        chunk_id = uuid.uuid4()
        doc = MagicMock()
        doc.collection_id = col_id  # matches → valid

        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=make_collection_orm(id=col_id))
        CONTEXT.chunk_repo.get_by_id = AsyncMock(
            return_value={
                "document_id": str(uuid.uuid4()),
                "raw_text": "The chunk text.",
                "prov": {"heading_path": "Section 1"},
            }
        )
        CONTEXT.document_repo.get_by_id = AsyncMock(return_value=doc)
        with patch(
            "backend.routers.collections.metagen.router.MetagenPreviewService.preview",
            new_callable=AsyncMock,
            return_value=_ok_result(),
        ):
            response = await client.post(
                _url(col_id),
                json={"field_name": "kw", "chunk_id": str(chunk_id)},
            )
        assert response.status_code == 200


# ─── CONFIG_WRITE capability gate ─────────────────────────────────────────────

class TestCapabilityGate:
    """POST /metagen/preview is gated by Capability.CONFIG_WRITE."""

    @pytest.mark.asyncio
    async def test_root_key_passes_capability_gate(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """Full-access root key → 200 (CONFIG_WRITE is implicitly granted)."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=make_collection_orm(id=col_id))
        with patch(
            "backend.routers.collections.metagen.router.MetagenPreviewService.preview",
            new_callable=AsyncMock,
            return_value=_ok_result(),
        ):
            response = await authed_client.post(
                _url(col_id), json=_body(), headers=_ROOT_HEADERS
            )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_scoped_key_without_config_write_gets_403(
        self, authed_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A scoped API key without config.write → 403 on POST /metagen/preview.

        permissions format: {"entries": [{"collection_id": "<uuid>", "role": "read"}]}.
        "read" expands to documents.read + search + config.read — no config.write.
        """
        col_id = uuid.uuid4()
        scoped = _scoped_principal(permissions={
            "entries": [{"collection_id": str(col_id), "role": "read"}]
        })

        async def _resolve(bearer: str | None) -> Principal | None:
            if bearer == "scoped-key":
                return scoped
            if bearer == _ROOT_API_KEY:
                return _ROOT_PRINCIPAL
            return None

        CONTEXT.auth_service.resolve_principal = AsyncMock(side_effect=_resolve)
        response = await authed_client.post(
            _url(col_id),
            json=_body(),
            headers={"Authorization": "Bearer scoped-key"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_scoped_key_with_config_write_passes(
        self, authed_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A scoped key that grants config.write on this collection → 200.

        permissions format: {"entries": [{"collection_id": "<uuid>", "role": "write"}]}.
        "write" expands to read caps + documents.write + config.write + chunks.write.
        """
        col_id = uuid.uuid4()
        scoped = _scoped_principal(permissions={
            "entries": [{"collection_id": str(col_id), "role": "write"}]
        })

        async def _resolve(bearer: str | None) -> Principal | None:
            if bearer == "scoped-write-key":
                return scoped
            if bearer == _ROOT_API_KEY:
                return _ROOT_PRINCIPAL
            return None

        CONTEXT.auth_service.resolve_principal = AsyncMock(side_effect=_resolve)
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=make_collection_orm(id=col_id))
        with patch(
            "backend.routers.collections.metagen.router.MetagenPreviewService.preview",
            new_callable=AsyncMock,
            return_value=_ok_result(),
        ):
            response = await authed_client.post(
                _url(col_id),
                json=_body(),
                headers={"Authorization": "Bearer scoped-write-key"},
            )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_no_credential_on_auth_on_returns_401(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """No Authorization header when auth is enabled → 401 (not 403)."""
        response = await authed_client.post(_url(uuid.uuid4()), json=_body())
        assert response.status_code == 401
