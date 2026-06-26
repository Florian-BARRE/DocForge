# ====== Code Summary ======
# End-to-end API tests for the keys-only auth model with AUTH_ENABLED=true.
#
# Model under test (AUTH-A):
#   - Only the root account logs in (password JWT) or presents the static root env key → FULL access.
#   - Delegated access is a permissioned API key: its `permissions` scope grants per-collection
#     capabilities (documents.read/write, search, config.read/write, chunks.write, collection.admin).
#   - A NULL permissions scope = full access (back-compat / static root key).
#
# Integration approach: "auth-on fixture" (not global header churn).
#   - The default `client` fixture keeps AUTH_ENABLED=False so all other tests need no headers.
#   - `authed_client` flips AUTH_ENABLED=True and programs mock_auth_service to accept the static
#     root key (full access). Scoped-key scenarios program resolve_principal to return a Principal
#     carrying a `permissions` scope; the capability gates then enforce per-collection access.
#
# Covered:
#   1. Unauthenticated → 401 (+ WWW-Authenticate, wrong scheme, invalid token).
#   2. Static root key → 200 (full access).
#   3. Login happy / bad password / empty body / inactive account → 200 / 401 / 422 / 401.
#   4. GET /auth/me → root identity (no grants/impersonated_by fields).
#   5. require_capability: scoped read key — read route 200, write route 403, other collection 403,
#      no matching entry 403; full-access principal passes everything.
#   6. Removed surfaces (/users, /collections/{id}/access, /users/{id}/impersonate) → 404.
#   7. POST /auth/keys: plaintext once + permissions echoed; invalid permissions → 422.
#   8. GET /auth/keys: returns permissions, never hash/plaintext.
#   9. DELETE /auth/keys/{id}: revoke scoped to owner.
#  10. DB API key boundary; null-permission key = full access (back-compat).
#  11. SSE ?token= auth.

# ====== Standard Library Imports ======
import uuid
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

# ====== Third-Party Library Imports ======
import httpx
import pytest
import pytest_asyncio

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.auth.models import Principal
from common_libs.storage.postgres.models import UserRole

# ── Shared constants ─────────────────────────────────────────────────────────

_ROOT_API_KEY = "test-root-static-api-key"
_ROOT_HEADERS = {"Authorization": f"Bearer {_ROOT_API_KEY}"}
_ROOT_USER_ID = uuid.uuid4()
# Full-access root principal (permissions=None → bypasses every per-capability check).
_ROOT_PRINCIPAL = Principal(
    user_id=_ROOT_USER_ID,
    username="root",
    global_role=UserRole.ROOT,
    is_root=True,
    permissions=None,
)


def _scoped_principal(*, permissions: dict | None) -> Principal:
    """Build an API-key principal (owned by root) carrying a permissions scope."""
    return Principal(
        user_id=_ROOT_USER_ID,
        username="root",
        global_role=UserRole.ROOT,
        is_root=True,
        permissions=permissions,
    )


# ── Auth-on fixture ───────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def authed_client(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[httpx.AsyncClient]:
    """
    Enable auth and program the mock auth service: the static root key → full-access root principal;
    anything else → None (unauthenticated). Individual tests override resolve_principal to inject a
    scoped API-key principal.
    """
    # 1. Enable auth on the mock RUNTIME_CONFIG
    monkeypatch.setattr(CONTEXT.RUNTIME_CONFIG, "AUTH_ENABLED", True, raising=False)

    # 2. Root key → root principal; everything else → None
    async def _resolve(bearer: str | None) -> Principal | None:
        return _ROOT_PRINCIPAL if bearer == _ROOT_API_KEY else None

    CONTEXT.auth_service.resolve_principal = AsyncMock(side_effect=_resolve)
    yield client


def _wire_doc_list_ok(collection_id: uuid.UUID) -> None:
    """Wire the repos so GET /documents/list returns 200 for a granted read key."""
    mock_col = MagicMock()
    mock_col.id = collection_id
    mock_col.pipeline_version = "v1"
    mock_col.needs_reindex = False
    CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=mock_col)
    CONTEXT.document_repo.count_by_collection = AsyncMock(return_value=0)
    CONTEXT.document_repo.list_by_collection = AsyncMock(return_value=[])
    CONTEXT.config_repo.list_versions = AsyncMock(return_value=[])


# ── 1. Unauthenticated → 401 ─────────────────────────────────────────────────

class TestUnauthenticated:
    """A protected route returns 401 when no valid credential is sent (auth on)."""

    @pytest.mark.asyncio
    async def test_no_header_returns_401(self, authed_client: httpx.AsyncClient) -> None:
        """GET /auth/me without credentials → 401."""
        response = await authed_client.get("/api/v1/auth/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_no_header_response_has_www_authenticate(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """401 response carries the WWW-Authenticate header."""
        response = await authed_client.get("/api/v1/auth/me")
        assert "www-authenticate" in response.headers

    @pytest.mark.asyncio
    async def test_wrong_scheme_returns_401(self, authed_client: httpx.AsyncClient) -> None:
        """A non-Bearer scheme (e.g. Basic) is rejected as unauthenticated."""
        response = await authed_client.get(
            "/api/v1/auth/me", headers={"Authorization": "Basic dXNlcjpwYXNz"}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self, authed_client: httpx.AsyncClient) -> None:
        """A Bearer token that does not resolve to any principal → 401."""
        response = await authed_client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer garbage-token"}
        )
        assert response.status_code == 401


# ── 2. Root key → 200 ────────────────────────────────────────────────────────

class TestRootKeyPasses:
    """The static root API key (full access) is accepted by protected routes."""

    @pytest.mark.asyncio
    async def test_root_key_get_me_returns_200(self, authed_client: httpx.AsyncClient) -> None:
        """GET /auth/me with root key → 200."""
        response = await authed_client.get("/api/v1/auth/me", headers=_ROOT_HEADERS)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_root_key_me_response_shape(self, authed_client: httpx.AsyncClient) -> None:
        """GET /auth/me with root key → body has user.role == 'root' and no grants field."""
        response = await authed_client.get("/api/v1/auth/me", headers=_ROOT_HEADERS)
        body = response.json()
        assert body["user"]["role"] == "root"
        # The collaborators model is gone — these fields must not be present anymore.
        assert "grants" not in body
        assert "impersonated_by" not in body


# ── 3. POST /auth/login ───────────────────────────────────────────────────────

class TestLogin:
    """Login endpoint — issues a JWT on correct credentials, hides failure reasons."""

    @pytest.mark.asyncio
    async def test_login_ok_returns_token(self, authed_client: httpx.AsyncClient) -> None:
        """Valid credentials → 200 with access_token + token_type bearer."""
        CONTEXT.auth_service.authenticate = AsyncMock(return_value=_ROOT_PRINCIPAL)
        CONTEXT.auth_service.mint_token = MagicMock(return_value="test-jwt-token")
        response = await authed_client.post(
            "/api/v1/auth/login", json={"username": "root", "password": "correct"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["access_token"] == "test-jwt-token"
        assert body["token_type"] == "bearer"
        assert body["user"]["role"] == "root"

    @pytest.mark.asyncio
    async def test_login_bad_password_returns_401(self, authed_client: httpx.AsyncClient) -> None:
        """Invalid credentials → 401 (authenticate returns None)."""
        CONTEXT.auth_service.authenticate = AsyncMock(return_value=None)
        response = await authed_client.post(
            "/api/v1/auth/login", json={"username": "root", "password": "wrong"}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_empty_body_returns_422(self, authed_client: httpx.AsyncClient) -> None:
        """Missing required fields → 422 from Pydantic validation."""
        response = await authed_client.post("/api/v1/auth/login", json={})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_inactive_user_401_does_not_leak_reason(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """Inactive account collapses to 401 and the body never leaks the reason."""
        CONTEXT.auth_service.authenticate = AsyncMock(return_value=None)
        response = await authed_client.post(
            "/api/v1/auth/login", json={"username": "alice", "password": "right"}
        )
        assert response.status_code == 401
        detail = response.json().get("detail", "")
        for leaked in ("inactive", "deactivated", "disabled", "account"):
            assert leaked not in detail.lower()


# ── 4. GET /auth/me ───────────────────────────────────────────────────────────

class TestMe:
    """GET /auth/me — root identity only (no grants/impersonation surface)."""

    @pytest.mark.asyncio
    async def test_me_is_root_identity(self, authed_client: httpx.AsyncClient) -> None:
        """A valid credential returns the root user summary."""
        response = await authed_client.get("/api/v1/auth/me", headers=_ROOT_HEADERS)
        assert response.status_code == 200
        body = response.json()
        assert body["user"]["username"] == "root"
        assert body["user"]["id"] == str(_ROOT_USER_ID)


# ── 5. require_capability enforcement ─────────────────────────────────────────

class TestCapabilityEnforcement:
    """
    A scoped API key is allowed exactly the capabilities its entries grant on the path collection.

    A 'read' role on collection A → documents.read/search/config.read on A only.
    """

    @pytest.mark.asyncio
    async def test_read_key_allowed_on_documents_list(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """A read-scoped key (collection A) can GET A's documents (documents.read)."""
        col_a = uuid.uuid4()
        principal = _scoped_principal(
            permissions={"entries": [{"collection_id": str(col_a), "role": "read"}]}
        )
        CONTEXT.auth_service.resolve_principal = AsyncMock(return_value=principal)
        _wire_doc_list_ok(col_a)

        response = await authed_client.get(
            f"/api/v1/collections/{col_a}/documents/list",
            headers={"Authorization": "Bearer scoped-read-key"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_read_key_blocked_on_ingest(self, authed_client: httpx.AsyncClient) -> None:
        """A read-scoped key cannot POST ingest (needs documents.write) → 403."""
        col_a = uuid.uuid4()
        principal = _scoped_principal(
            permissions={"entries": [{"collection_id": str(col_a), "role": "read"}]}
        )
        CONTEXT.auth_service.resolve_principal = AsyncMock(return_value=principal)

        response = await authed_client.post(
            f"/api/v1/collections/{col_a}/documents/ingest",
            headers={"Authorization": "Bearer scoped-read-key"},
            files={"file": ("x.pdf", b"data", "application/pdf")},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_read_key_blocked_on_other_collection(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """A key scoped to A is denied on a different collection B → 403."""
        col_a, col_b = uuid.uuid4(), uuid.uuid4()
        principal = _scoped_principal(
            permissions={"entries": [{"collection_id": str(col_a), "role": "read"}]}
        )
        CONTEXT.auth_service.resolve_principal = AsyncMock(return_value=principal)

        response = await authed_client.get(
            f"/api/v1/collections/{col_b}/documents/list",
            headers={"Authorization": "Bearer scoped-read-key"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_write_key_can_ingest(self, authed_client: httpx.AsyncClient) -> None:
        """A write-scoped key passes the ingest capability gate (then 400 on empty file)."""
        col_a = uuid.uuid4()
        principal = _scoped_principal(
            permissions={"entries": [{"collection_id": str(col_a), "role": "write"}]}
        )
        CONTEXT.auth_service.resolve_principal = AsyncMock(return_value=principal)

        # Empty file → the handler's own 400 guard fires, proving the capability gate let it through.
        response = await authed_client.post(
            f"/api/v1/collections/{col_a}/documents/ingest",
            headers={"Authorization": "Bearer scoped-write-key"},
            files={"file": ("x.pdf", b"", "application/pdf")},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_wildcard_admin_passes_collection_delete(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """A '*' admin key grants collection.admin on any collection → delete proceeds (200)."""
        col_id = uuid.uuid4()
        principal = _scoped_principal(
            permissions={"entries": [{"collection_id": "*", "role": "admin"}]}
        )
        CONTEXT.auth_service.resolve_principal = AsyncMock(return_value=principal)
        mock_col = MagicMock()
        mock_col.id = col_id
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=mock_col)
        CONTEXT.document_repo.list_source_hashes = AsyncMock(return_value=[])
        CONTEXT.collection_repo.delete = AsyncMock()

        response = await authed_client.delete(
            f"/api/v1/collections/{col_id}/delete",
            headers={"Authorization": "Bearer wildcard-admin-key"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_write_key_blocked_on_collection_delete(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """A write key lacks collection.admin → delete is 403."""
        col_id = uuid.uuid4()
        principal = _scoped_principal(
            permissions={"entries": [{"collection_id": str(col_id), "role": "write"}]}
        )
        CONTEXT.auth_service.resolve_principal = AsyncMock(return_value=principal)

        response = await authed_client.delete(
            f"/api/v1/collections/{col_id}/delete",
            headers={"Authorization": "Bearer scoped-write-key"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_full_access_principal_passes_every_gate(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """The root (permissions=None) full-access principal passes a write gate."""
        col_id = uuid.uuid4()
        mock_col = MagicMock()
        mock_col.id = col_id
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=mock_col)
        CONTEXT.document_repo.list_source_hashes = AsyncMock(return_value=[])
        CONTEXT.collection_repo.delete = AsyncMock()

        response = await authed_client.delete(
            f"/api/v1/collections/{col_id}/delete", headers=_ROOT_HEADERS
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_null_permission_key_is_full_access(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """A legacy DB key with NULL permissions resolves to a full-access principal (back-compat)."""
        col_a = uuid.uuid4()
        principal = _scoped_principal(permissions=None)  # NULL scope = full access
        CONTEXT.auth_service.resolve_principal = AsyncMock(return_value=principal)
        _wire_doc_list_ok(col_a)

        response = await authed_client.get(
            f"/api/v1/collections/{col_a}/documents/list",
            headers={"Authorization": "Bearer legacy-null-key"},
        )
        assert response.status_code == 200


# ── 6. Removed surfaces → 404 ─────────────────────────────────────────────────

class TestRemovedRoutes:
    """The users / collaborators / impersonation surfaces are gone (router not mounted)."""

    @pytest.mark.asyncio
    async def test_users_list_is_404(self, authed_client: httpx.AsyncClient) -> None:
        """GET /api/v1/users → 404 (router removed)."""
        response = await authed_client.get("/api/v1/users", headers=_ROOT_HEADERS)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_collection_access_is_404(self, authed_client: httpx.AsyncClient) -> None:
        """GET /api/v1/collections/{id}/access → 404 (collaborators removed)."""
        response = await authed_client.get(
            f"/api/v1/collections/{uuid.uuid4()}/access", headers=_ROOT_HEADERS
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_impersonate_is_404(self, authed_client: httpx.AsyncClient) -> None:
        """POST /api/v1/users/{id}/impersonate → 404 (impersonation removed)."""
        response = await authed_client.post(
            f"/api/v1/users/{uuid.uuid4()}/impersonate", headers=_ROOT_HEADERS
        )
        assert response.status_code == 404


# ── 7. POST /auth/keys — create with permissions ──────────────────────────────

class TestApiKeyCreate:
    """POST /auth/keys returns the plaintext once + echoes the scope; validates permissions."""

    def _mock_key_orm(self, *, permissions: dict | None) -> MagicMock:
        import datetime
        k = MagicMock()
        k.id = uuid.uuid4()
        k.name = "my-key"
        k.prefix = "plaintex"
        k.permissions = permissions
        k.created_at = datetime.datetime.now()
        return k

    @pytest.mark.asyncio
    async def test_create_scoped_key_returns_plaintext_and_permissions(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """Creating a scoped key → 201 with plaintext key + the permissions echoed back."""
        perms = {"entries": [{"collection_id": str(uuid.uuid4()), "role": "read"}]}
        CONTEXT.auth_service.generate_api_key = MagicMock(
            return_value=("plaintext-key-value", "sha256hash", "plaintex")
        )
        CONTEXT.api_key_repo.create = AsyncMock(
            return_value=self._mock_key_orm(permissions=perms)
        )

        response = await authed_client.post(
            "/api/v1/auth/keys",
            json={"name": "my-key", "permissions": perms},
            headers=_ROOT_HEADERS,
        )
        assert response.status_code == 201
        body = response.json()
        assert body["key"] == "plaintext-key-value"
        assert body["permissions"] == perms

    @pytest.mark.asyncio
    async def test_create_key_without_permissions_is_rejected(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """Omitting permissions → 422 (no fail-open). A created key MUST declare its scope;
        the unscoped full-access sentinel is reserved for the static root env key."""
        response = await authed_client.post(
            "/api/v1/auth/keys", json={"name": "my-key"}, headers=_ROOT_HEADERS
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_permissions_returns_422(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """A permissions scope with an unknown role → 422 (validated against the taxonomy)."""
        bad = {"entries": [{"collection_id": "*", "role": "superadmin"}]}
        response = await authed_client.post(
            "/api/v1/auth/keys",
            json={"name": "bad-key", "permissions": bad},
            headers=_ROOT_HEADERS,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_custom_without_capabilities_returns_422(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """A custom entry missing its capabilities list → 422."""
        bad = {"entries": [{"collection_id": "*", "role": "custom"}]}
        response = await authed_client.post(
            "/api/v1/auth/keys",
            json={"name": "bad-key", "permissions": bad},
            headers=_ROOT_HEADERS,
        )
        assert response.status_code == 422


# ── 8. GET /auth/keys — listing exposes scope, never secrets ──────────────────

class TestApiKeyList:
    """GET /auth/keys returns the per-collection scope but never the hash/plaintext."""

    @pytest.mark.asyncio
    async def test_list_returns_permissions_no_secrets(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """List items carry permissions + prefix, never 'key'/'key_hash'."""
        import datetime
        perms = {"entries": [{"collection_id": "*", "role": "admin"}]}
        mock_key = MagicMock()
        mock_key.id = uuid.uuid4()
        mock_key.name = "stored-key"
        mock_key.prefix = "abc12345"
        mock_key.permissions = perms
        mock_key.created_at = datetime.datetime.now()
        mock_key.last_used_at = None
        mock_key.revoked_at = None
        CONTEXT.api_key_repo.list_for_user = AsyncMock(return_value=[mock_key])

        response = await authed_client.get("/api/v1/auth/keys", headers=_ROOT_HEADERS)
        assert response.status_code == 200
        item = response.json()["keys"][0]
        assert item["permissions"] == perms
        assert "key" not in item
        assert "key_hash" not in item


# ── 9. DELETE /auth/keys/{id} — revoke scoped to owner ────────────────────────

class TestApiKeyRevoke:
    """Revoke an API key — scoped to owner; non-existent/foreign key → 404."""

    @pytest.mark.asyncio
    async def test_revoke_own_key_returns_200(self, authed_client: httpx.AsyncClient) -> None:
        """Revoking an existing key owned by the caller → 200 with revoked=true."""
        key_id = uuid.uuid4()
        CONTEXT.api_key_repo.revoke = AsyncMock(return_value=True)
        response = await authed_client.delete(
            f"/api/v1/auth/keys/{key_id}", headers=_ROOT_HEADERS
        )
        assert response.status_code == 200
        assert response.json()["revoked"] is True

    @pytest.mark.asyncio
    async def test_revoke_unknown_key_returns_404(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """Revoking a key that doesn't exist (or belongs to another user) → 404."""
        CONTEXT.api_key_repo.revoke = AsyncMock(return_value=False)
        response = await authed_client.delete(
            f"/api/v1/auth/keys/{uuid.uuid4()}", headers=_ROOT_HEADERS
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_revoke_is_scoped_to_owner(self, authed_client: httpx.AsyncClient) -> None:
        """The revoke call passes the caller's user_id to the repo (owner-scoping)."""
        key_id = uuid.uuid4()
        CONTEXT.api_key_repo.revoke = AsyncMock(return_value=True)
        await authed_client.delete(f"/api/v1/auth/keys/{key_id}", headers=_ROOT_HEADERS)
        CONTEXT.api_key_repo.revoke.assert_awaited_once()
        call_args = CONTEXT.api_key_repo.revoke.call_args
        called_user_id = call_args.args[2] if len(call_args.args) > 2 else call_args.kwargs.get("user_id")
        assert called_user_id == _ROOT_USER_ID


# ── 10. DB API key boundary ───────────────────────────────────────────────────

class TestDbApiKeyBoundary:
    """A resolved API-key principal is accepted at the HTTP boundary; junk → 401."""

    @pytest.mark.asyncio
    async def test_scoped_key_bearer_accepted_on_me(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """A bearer resolving to a scoped key principal → 200 on /auth/me."""
        principal = _scoped_principal(
            permissions={"entries": [{"collection_id": "*", "role": "read"}]}
        )

        async def _resolve(bearer: str | None) -> Principal | None:
            return principal if bearer == "docforge_dbkey" else None

        CONTEXT.auth_service.resolve_principal = AsyncMock(side_effect=_resolve)
        response = await authed_client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer docforge_dbkey"}
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_unresolvable_bearer_returns_401(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """A bearer that matches nothing → 401."""
        CONTEXT.auth_service.resolve_principal = AsyncMock(return_value=None)
        response = await authed_client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer nope"}
        )
        assert response.status_code == 401


# ── 11. SSE ?token= auth ──────────────────────────────────────────────────────

class TestSseTokenAuth:
    """SSE routes accept the bearer via header OR ?token=; non-SSE routes ignore ?token=."""

    @staticmethod
    def _patch_sse_stream(monkeypatch: pytest.MonkeyPatch) -> None:
        """Patch SseHelpers.stream to return an empty SSE response without a real broadcaster."""
        from sse_starlette.sse import EventSourceResponse

        monkeypatch.setattr(CONTEXT, "event_broadcaster", MagicMock(), raising=False)

        async def _empty_gen():
            return
            yield  # type: ignore[misc]

        def _fake_stream(broadcaster, *, keepalive, predicate=None):  # noqa: ANN001
            return EventSourceResponse(_empty_gen(), ping=keepalive)

        import importlib
        _mon = importlib.import_module("backend.routers.monitoring.router")
        monkeypatch.setattr(_mon.SseHelpers, "stream", staticmethod(_fake_stream), raising=True)

    @pytest.mark.asyncio
    async def test_sse_query_token_accepted(
        self, authed_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GET /monitoring/stream?token=<root-key> with no header → 200."""
        self._patch_sse_stream(monkeypatch)
        monkeypatch.setattr(CONTEXT.RUNTIME_CONFIG, "SSE_KEEPALIVE_SECONDS", 15, raising=False)
        response = await authed_client.get(
            f"/api/v1/monitoring/stream?token={_ROOT_API_KEY}"
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_sse_no_auth_returns_401(self, authed_client: httpx.AsyncClient) -> None:
        """GET /monitoring/stream with no header AND no ?token= → 401."""
        response = await authed_client.get("/api/v1/monitoring/stream")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_non_sse_route_ignores_query_token(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """A non-SSE route reads the header only — ?token= is rejected → 401."""
        response = await authed_client.get(f"/api/v1/auth/me?token={_ROOT_API_KEY}")
        assert response.status_code == 401
