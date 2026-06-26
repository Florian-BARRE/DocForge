# ====== Code Summary ======
# End-to-end API tests for the auth + per-collection authorization layer with AUTH_ENABLED=true.
#
# Integration approach: "auth-on fixture" (not global header churn).
#   - The default `client` fixture keeps AUTH_ENABLED=False so all 418 existing tests need
#     no Authorization headers.
#   - These tests use a local `authed_client` fixture that overrides
#     CONTEXT.RUNTIME_CONFIG.AUTH_ENABLED=True and programs mock_auth_service to accept a known
#     static root API key, returning a root Principal.  Non-root scenarios are exercised by
#     programming mock_auth_service.resolve_principal and mock_auth_service.effective_collection_role
#     to return user-scoped principals / role decisions per test.
#
# What is covered:
#   1. Unauthenticated request to a protected route → 401.
#   2. Authenticated with root key → 200 (pass-through).
#   3. POST /auth/login happy path (mock authenticate returns principal) → 200 + token.
#   4. POST /auth/login bad password (mock authenticate returns None) → 401.
#   5. GET /auth/me → user summary + grants list.
#   6. require_collection_role: read user blocked on a write route → 403;
#      allowed on a read route → 200.
#   7. require_collection_role: user with no grant → 403.
#   8. users router: non-root caller → 403.
#   9. POST /auth/keys returns plaintext key once; GET /auth/keys list never exposes hash/plaintext.
#  10. DELETE /auth/keys/{id} revoke — success → revoked:true; key not found / wrong owner → 404.

# ====== Standard Library Imports ======
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

# ====== Third-Party Library Imports ======
import httpx
import pytest
import pytest_asyncio

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.auth.models import Principal
from common_libs.storage.postgres.models import GrantRole, UserRole

# ── Shared constants ─────────────────────────────────────────────────────────

_ROOT_API_KEY = "test-root-static-api-key"
_ROOT_HEADERS = {"Authorization": f"Bearer {_ROOT_API_KEY}"}
_ROOT_USER_ID = uuid.uuid4()
_ROOT_PRINCIPAL = Principal(
    user_id=_ROOT_USER_ID,
    username="root",
    global_role=UserRole.ROOT,
    is_root=True,
)
_USER_ID = uuid.uuid4()
_USER_PRINCIPAL = Principal(
    user_id=_USER_ID,
    username="alice",
    global_role=UserRole.USER,
    is_root=False,
)


# ── Auth-on fixture ───────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def authed_client(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[httpx.AsyncClient]:
    """
    Override CONTEXT to enable auth and program the mock auth service.

    The default ``mock_auth_service`` fixture (injected by ``inject_context``) is wired to:
      - return ``_ROOT_PRINCIPAL`` when the static root API key is presented.
      - return ``None`` for everything else (unauthenticated).
      - return ``GrantRole.ADMIN`` for effective_collection_role of root.

    Individual tests that need non-root scenarios override
    ``CONTEXT.auth_service.resolve_principal`` and/or
    ``CONTEXT.auth_service.effective_collection_role`` directly.

    Why this approach (auth-on fixture, not global header):
      - 418 existing tests continue to run without Authorization headers.
      - A single focused fixture enables the full RBAC path without rebuilding the ASGI app.
      - The mock_auth_service already lives in CONTEXT (injected by inject_context); we only
        change the AUTH_ENABLED flag and the resolve_principal return value here.
    """
    # 1. Enable auth on the mock RUNTIME_CONFIG
    monkeypatch.setattr(CONTEXT.RUNTIME_CONFIG, "AUTH_ENABLED", True, raising=False)

    # 2. Program the mock auth service: root key → root principal; anything else → None
    async def _resolve(bearer: str | None) -> Principal | None:
        if bearer == _ROOT_API_KEY:
            return _ROOT_PRINCIPAL
        return None

    CONTEXT.auth_service.resolve_principal = AsyncMock(side_effect=_resolve)

    # 3. effective_collection_role: root → ADMIN (unchanged from default mock)
    CONTEXT.auth_service.effective_collection_role = AsyncMock(return_value=GrantRole.ADMIN)

    yield client


# ── 1. Unauthenticated → 401 ─────────────────────────────────────────────────

class TestUnauthenticated:
    """A protected route returns 401 when no Authorization header is sent (auth on)."""

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
    """The static root API key is accepted by protected routes."""

    @pytest.mark.asyncio
    async def test_root_key_get_me_returns_200(self, authed_client: httpx.AsyncClient) -> None:
        """GET /auth/me with root key → 200."""
        CONTEXT.grant_repo.list_collection_ids_for_user = AsyncMock(return_value=[])
        response = await authed_client.get("/api/v1/auth/me", headers=_ROOT_HEADERS)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_root_key_me_response_shape(self, authed_client: httpx.AsyncClient) -> None:
        """GET /auth/me with root key → body has user.role == 'root' and empty grants."""
        CONTEXT.grant_repo.list_collection_ids_for_user = AsyncMock(return_value=[])
        response = await authed_client.get("/api/v1/auth/me", headers=_ROOT_HEADERS)
        body = response.json()
        assert body["user"]["role"] == "root"
        assert body["grants"] == []


# ── 3. POST /auth/login happy path ────────────────────────────────────────────

class TestLogin:
    """Login endpoint — issues a JWT on correct credentials."""

    @pytest.mark.asyncio
    async def test_login_ok_returns_200(self, authed_client: httpx.AsyncClient) -> None:
        """Valid credentials → 200 with access_token."""
        CONTEXT.auth_service.authenticate = AsyncMock(return_value=_ROOT_PRINCIPAL)
        CONTEXT.auth_service.mint_token = MagicMock(return_value="test-jwt-token")

        response = await authed_client.post(
            "/api/v1/auth/login",
            json={"username": "root", "password": "correct-password"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_login_ok_response_has_token(self, authed_client: httpx.AsyncClient) -> None:
        """Successful login body contains access_token and token_type='bearer'."""
        CONTEXT.auth_service.authenticate = AsyncMock(return_value=_ROOT_PRINCIPAL)
        CONTEXT.auth_service.mint_token = MagicMock(return_value="test-jwt-token")

        response = await authed_client.post(
            "/api/v1/auth/login",
            json={"username": "root", "password": "correct-password"},
        )
        body = response.json()
        assert body["access_token"] == "test-jwt-token"
        assert body["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_ok_response_has_user(self, authed_client: httpx.AsyncClient) -> None:
        """Successful login body contains a user summary (id, username, role)."""
        CONTEXT.auth_service.authenticate = AsyncMock(return_value=_ROOT_PRINCIPAL)
        CONTEXT.auth_service.mint_token = MagicMock(return_value="test-jwt-token")

        response = await authed_client.post(
            "/api/v1/auth/login",
            json={"username": "root", "password": "correct-password"},
        )
        body = response.json()
        for field in ("id", "username", "role"):
            assert field in body["user"]

    @pytest.mark.asyncio
    async def test_login_bad_password_returns_401(self, authed_client: httpx.AsyncClient) -> None:
        """Invalid credentials → 401. No information on whether username or password was wrong."""
        CONTEXT.auth_service.authenticate = AsyncMock(return_value=None)

        response = await authed_client.post(
            "/api/v1/auth/login",
            json={"username": "root", "password": "wrong-password"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_empty_body_returns_422(self, authed_client: httpx.AsyncClient) -> None:
        """Missing required fields in the login body → 422 from Pydantic validation."""
        response = await authed_client.post("/api/v1/auth/login", json={})
        assert response.status_code == 422


# ── 5. GET /auth/me for standard user ────────────────────────────────────────

class TestMe:
    """GET /auth/me — correct identity + grants for standard users."""

    @pytest.mark.asyncio
    async def test_me_user_shows_grants(self, authed_client: httpx.AsyncClient) -> None:
        """A non-root user sees their explicit per-collection grants."""
        # 1. Auth resolves to a standard user
        CONTEXT.auth_service.resolve_principal = AsyncMock(return_value=_USER_PRINCIPAL)

        # 2. Grant repo returns one grant
        col_id = uuid.uuid4()
        mock_grant = MagicMock()
        mock_grant.collection_id = col_id
        mock_grant.role = "read"

        CONTEXT.grant_repo.list_collection_ids_for_user = AsyncMock(return_value=[col_id])
        CONTEXT.grant_repo.get = AsyncMock(return_value=mock_grant)

        response = await authed_client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer user-token"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["user"]["username"] == "alice"
        assert len(body["grants"]) == 1
        assert body["grants"][0]["role"] == "read"


# ── 6. require_collection_role: read vs write ─────────────────────────────────

class TestCollectionRoleEnforcement:
    """
    require_collection_role: read user blocked on write routes; allowed on read routes.

    The DELETE /api/v1/collections/{id}/delete route requires ADMIN.
    The GET /api/v1/collections/list route only requires require_principal (no role gate).
    For a fine-grained read-vs-write gate we test the document-router:
      - GET /api/v1/collections/{id}/documents/list needs at least READ (read = allowed).
      - POST /api/v1/collections/{id}/documents/ingest needs at least WRITE (read = 403).
    """

    @pytest.mark.asyncio
    async def test_read_role_allowed_on_collection_list(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """
        A user with READ on the collection can list documents.

        The documents list route uses require_collection_role(GrantRole.READ) — the read user
        has exactly that, so the gate passes.
        """
        # 1. Resolve to non-root user
        CONTEXT.auth_service.resolve_principal = AsyncMock(return_value=_USER_PRINCIPAL)
        # 2. Grant check: READ role (enough for list)
        CONTEXT.auth_service.effective_collection_role = AsyncMock(return_value=GrantRole.READ)
        CONTEXT.document_repo.list_by_collection = AsyncMock(return_value=[])
        CONTEXT.document_repo.count_by_collection = AsyncMock(return_value=0)

        col_id = uuid.uuid4()
        response = await authed_client.get(
            f"/api/v1/collections/{col_id}/documents/list",
            headers={"Authorization": "Bearer user-token"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_read_role_blocked_on_delete_collection(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """A user with READ cannot delete a collection (requires ADMIN) → 403."""
        CONTEXT.auth_service.resolve_principal = AsyncMock(return_value=_USER_PRINCIPAL)
        # READ is below the ADMIN threshold required by delete_collection
        CONTEXT.auth_service.effective_collection_role = AsyncMock(return_value=GrantRole.READ)

        col_id = uuid.uuid4()
        response = await authed_client.delete(
            f"/api/v1/collections/{col_id}/delete",
            headers={"Authorization": "Bearer user-token"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_write_role_blocked_on_delete_collection(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """A user with WRITE cannot delete a collection (requires ADMIN) → 403."""
        CONTEXT.auth_service.resolve_principal = AsyncMock(return_value=_USER_PRINCIPAL)
        CONTEXT.auth_service.effective_collection_role = AsyncMock(return_value=GrantRole.WRITE)

        col_id = uuid.uuid4()
        response = await authed_client.delete(
            f"/api/v1/collections/{col_id}/delete",
            headers={"Authorization": "Bearer user-token"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_role_passes_delete_collection(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """A user with ADMIN can delete a collection (if it exists) → 200."""
        CONTEXT.auth_service.resolve_principal = AsyncMock(return_value=_USER_PRINCIPAL)
        CONTEXT.auth_service.effective_collection_role = AsyncMock(return_value=GrantRole.ADMIN)

        col_id = uuid.uuid4()
        # collection_repo.get_by_id must return a non-None collection for delete to proceed
        mock_col = MagicMock()
        mock_col.id = col_id
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=mock_col)
        CONTEXT.document_repo.list_source_hashes = AsyncMock(return_value=[])
        CONTEXT.collection_repo.delete = AsyncMock()

        response = await authed_client.delete(
            f"/api/v1/collections/{col_id}/delete",
            headers={"Authorization": "Bearer user-token"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_no_grant_returns_403(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """A user with no grant at all on the collection → 403 (not 404)."""
        CONTEXT.auth_service.resolve_principal = AsyncMock(return_value=_USER_PRINCIPAL)
        # None = no grant at all on this collection
        CONTEXT.auth_service.effective_collection_role = AsyncMock(return_value=None)

        col_id = uuid.uuid4()
        response = await authed_client.delete(
            f"/api/v1/collections/{col_id}/delete",
            headers={"Authorization": "Bearer user-token"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_root_passes_all_collection_gates(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """Root is always implicitly ADMIN — passes every require_collection_role gate."""
        # auth_service already returns GrantRole.ADMIN for root (default in authed_client fixture)
        col_id = uuid.uuid4()
        mock_col = MagicMock()
        mock_col.id = col_id
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=mock_col)
        CONTEXT.document_repo.list_source_hashes = AsyncMock(return_value=[])
        CONTEXT.collection_repo.delete = AsyncMock()

        response = await authed_client.delete(
            f"/api/v1/collections/{col_id}/delete",
            headers=_ROOT_HEADERS,
        )
        assert response.status_code == 200


# ── 8. Users router: non-root → 403 ─────────────────────────────────────────

class TestUsersRouterRootOnly:
    """The /api/v1/users router is gated by require_root — non-root gets 403."""

    @pytest.mark.asyncio
    async def test_list_users_non_root_returns_403(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """GET /users with a standard user → 403."""
        CONTEXT.auth_service.resolve_principal = AsyncMock(return_value=_USER_PRINCIPAL)
        response = await authed_client.get(
            "/api/v1/users", headers={"Authorization": "Bearer user-token"}
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_user_non_root_returns_403(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """POST /users with a standard user → 403."""
        CONTEXT.auth_service.resolve_principal = AsyncMock(return_value=_USER_PRINCIPAL)
        response = await authed_client.post(
            "/api/v1/users",
            json={"username": "newuser", "password": "pass123"},
            headers={"Authorization": "Bearer user-token"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_list_users_root_returns_200(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """GET /users with root key → 200 (root-only gate passes)."""
        CONTEXT.user_repo.list_users = AsyncMock(return_value=[])
        response = await authed_client.get("/api/v1/users", headers=_ROOT_HEADERS)
        assert response.status_code == 200


# ── 9. POST /auth/keys — create-once semantics ───────────────────────────────

class TestApiKeyCreate:
    """POST /auth/keys returns plaintext key ONCE; GET /auth/keys never exposes it."""

    @pytest.mark.asyncio
    async def test_create_key_returns_201(self, authed_client: httpx.AsyncClient) -> None:
        """Creating a key returns 201."""
        import datetime

        mock_key_orm = MagicMock()
        mock_key_orm.id = uuid.uuid4()
        mock_key_orm.name = "my-key"
        mock_key_orm.prefix = "plaintex"
        mock_key_orm.created_at = datetime.datetime.now()

        CONTEXT.api_key_repo.create = AsyncMock(return_value=mock_key_orm)
        # generate_api_key is a synchronous method on the mock
        CONTEXT.auth_service.generate_api_key = MagicMock(
            return_value=("plaintext-key-value", "sha256hash", "plaintex")
        )

        response = await authed_client.post(
            "/api/v1/auth/keys",
            json={"name": "my-key"},
            headers=_ROOT_HEADERS,
        )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_key_response_has_plaintext(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """The creation response carries the plaintext key field."""
        import datetime

        mock_key_orm = MagicMock()
        mock_key_orm.id = uuid.uuid4()
        mock_key_orm.name = "my-key"
        mock_key_orm.prefix = "plaintex"
        mock_key_orm.created_at = datetime.datetime.now()

        CONTEXT.api_key_repo.create = AsyncMock(return_value=mock_key_orm)
        CONTEXT.auth_service.generate_api_key = MagicMock(
            return_value=("plaintext-key-value", "sha256hash", "plaintex")
        )

        response = await authed_client.post(
            "/api/v1/auth/keys",
            json={"name": "my-key"},
            headers=_ROOT_HEADERS,
        )
        body = response.json()
        assert "key" in body
        assert body["key"] == "plaintext-key-value"

    @pytest.mark.asyncio
    async def test_list_keys_never_returns_hash_or_plaintext(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """GET /auth/keys response items never include 'key' (plaintext) or 'key_hash'."""
        import datetime

        mock_key = MagicMock()
        mock_key.id = uuid.uuid4()
        mock_key.name = "stored-key"
        mock_key.prefix = "abc12345"
        mock_key.created_at = datetime.datetime.now()
        mock_key.last_used_at = None
        mock_key.revoked_at = None

        CONTEXT.api_key_repo.list_for_user = AsyncMock(return_value=[mock_key])

        response = await authed_client.get("/api/v1/auth/keys", headers=_ROOT_HEADERS)
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        item = body["keys"][0]
        # Plaintext key and hash must never appear in the listing
        assert "key" not in item
        assert "key_hash" not in item
        assert "hash" not in item
        # Only safe fields should be present
        assert "prefix" in item
        assert "name" in item


# ── 10. DELETE /auth/keys/{id} — revoke scoped to owner ──────────────────────

class TestApiKeyRevoke:
    """Revoke an API key — scoped to owner; non-existent/foreign key → 404."""

    @pytest.mark.asyncio
    async def test_revoke_own_key_returns_200(self, authed_client: httpx.AsyncClient) -> None:
        """Revoking an existing key owned by the caller → 200 with revoked=true."""
        key_id = uuid.uuid4()
        CONTEXT.api_key_repo.revoke = AsyncMock(return_value=True)

        response = await authed_client.delete(
            f"/api/v1/auth/keys/{key_id}",
            headers=_ROOT_HEADERS,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["revoked"] is True
        assert body["id"] == str(key_id)

    @pytest.mark.asyncio
    async def test_revoke_unknown_key_returns_404(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """Revoking a key that doesn't exist (or belongs to another user) → 404."""
        key_id = uuid.uuid4()
        # revoke() returns False when the key is not found / not owned by caller
        CONTEXT.api_key_repo.revoke = AsyncMock(return_value=False)

        response = await authed_client.delete(
            f"/api/v1/auth/keys/{key_id}",
            headers=_ROOT_HEADERS,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_revoke_is_scoped_to_owner(self, authed_client: httpx.AsyncClient) -> None:
        """
        The revoke call passes the caller's user_id to the repo — owner-scoping is enforced
        at the repo layer, not just by convention.
        """
        key_id = uuid.uuid4()
        CONTEXT.api_key_repo.revoke = AsyncMock(return_value=True)

        await authed_client.delete(
            f"/api/v1/auth/keys/{key_id}",
            headers=_ROOT_HEADERS,
        )

        # The repo must have been called with the root principal's user_id
        CONTEXT.api_key_repo.revoke.assert_awaited_once()
        call_args = CONTEXT.api_key_repo.revoke.call_args
        # revoke(session, key_id, user_id) — positional or keyword
        called_key_id = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("key_id")
        called_user_id = call_args.args[2] if len(call_args.args) > 2 else call_args.kwargs.get("user_id")
        assert called_key_id == key_id
        assert called_user_id == _ROOT_USER_ID


# ── 4b. POST /auth/login with inactive user → 401 ────────────────────────────

class TestLoginInactiveUser:
    """
    POST /auth/login collapses bad-password, unknown-user AND inactive-account to 401.

    This is the HTTP-boundary gap that was reported after the initial auth pass:
    authenticate() returns None for inactive accounts, and the route always converts
    None → 401 without distinguishing the reason (deliberate information hiding).
    """

    @pytest.mark.asyncio
    async def test_inactive_user_returns_401(self, authed_client: httpx.AsyncClient) -> None:
        """Correct username + password for a deactivated account → 401 at the HTTP boundary."""
        # authenticate() returns None for inactive accounts (same as bad password)
        CONTEXT.auth_service.authenticate = AsyncMock(return_value=None)

        response = await authed_client.post(
            "/api/v1/auth/login",
            json={"username": "deactivated-alice", "password": "correct-password"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_inactive_user_401_detail_does_not_leak_reason(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """The 401 body does not reveal whether the account is inactive vs bad credentials."""
        CONTEXT.auth_service.authenticate = AsyncMock(return_value=None)

        response = await authed_client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "right-password"},
        )
        body = response.json()
        detail = body.get("detail", "")
        # "inactive", "deactivated", "disabled" must not appear — information hiding
        for leaked_word in ("inactive", "deactivated", "disabled", "account"):
            assert leaked_word not in detail.lower(), (
                f"Detail leaks account state via word {leaked_word!r}: {detail!r}"
            )


# ── 11. DELETE /api/v1/users/{user_id} — deactivate ─────────────────────────

class TestDeactivateUser:
    """
    DELETE /api/v1/users/{user_id} — root-only soft deactivation.

    Behaviour read from router source:
      - Root succeeds on a known user → 200 with deactivated=true.
      - Non-root → 403 (require_root gate).
      - Known user not found → 404.
      - Root trying to deactivate itself → 409 (self-lockout guard).
    """

    def _make_user_orm(self, user_id: uuid.UUID) -> MagicMock:
        """Minimal mock user ORM row for deactivation tests."""
        import datetime
        user = MagicMock()
        user.id = user_id
        user.username = "alice"
        user.role = "user"
        user.is_active = False  # returned AFTER deactivation
        user.created_at = datetime.datetime.now()
        return user

    @pytest.mark.asyncio
    async def test_root_deactivates_known_user_returns_200(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """Root successfully deactivates a user → 200, deactivated=true."""
        target_id = uuid.uuid4()
        CONTEXT.user_repo.set_active = AsyncMock(return_value=self._make_user_orm(target_id))

        response = await authed_client.delete(
            f"/api/v1/users/{target_id}",
            headers=_ROOT_HEADERS,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["deactivated"] is True
        assert body["id"] == str(target_id)

    @pytest.mark.asyncio
    async def test_non_root_returns_403(self, authed_client: httpx.AsyncClient) -> None:
        """A standard user cannot deactivate anyone → 403."""
        CONTEXT.auth_service.resolve_principal = AsyncMock(return_value=_USER_PRINCIPAL)
        target_id = uuid.uuid4()

        response = await authed_client.delete(
            f"/api/v1/users/{target_id}",
            headers={"Authorization": "Bearer user-token"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_unknown_user_returns_404(self, authed_client: httpx.AsyncClient) -> None:
        """Deactivating a user id that does not exist → 404."""
        CONTEXT.user_repo.set_active = AsyncMock(return_value=None)

        response = await authed_client.delete(
            f"/api/v1/users/{uuid.uuid4()}",
            headers=_ROOT_HEADERS,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_root_cannot_deactivate_itself_returns_409(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """Root deactivating its own account → 409 (self-lockout guard)."""
        # The route compares user_id against root.user_id — use the root principal's id
        response = await authed_client.delete(
            f"/api/v1/users/{_ROOT_USER_ID}",
            headers=_ROOT_HEADERS,
        )
        assert response.status_code == 409


# ── 12. PUT /api/v1/users/{user_id}/password — reset ────────────────────────

class TestResetPassword:
    """
    PUT /api/v1/users/{user_id}/password — root-only password reset.

    Behaviour:
      - Root resets a known user's password → 200 with the updated UserResponse.
      - Non-root → 403.
      - Unknown user id → 404.
    """

    def _make_user_orm(self, user_id: uuid.UUID) -> MagicMock:
        """Minimal mock user ORM row for password-reset tests."""
        import datetime
        user = MagicMock()
        user.id = user_id
        user.username = "bob"
        user.role = "user"
        user.is_active = True
        user.created_at = datetime.datetime.now()
        return user

    @pytest.mark.asyncio
    async def test_root_resets_password_returns_200(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """Root successfully resets a user's password → 200 with user data (no hash)."""
        target_id = uuid.uuid4()
        CONTEXT.user_repo.update_password = AsyncMock(
            return_value=self._make_user_orm(target_id)
        )

        response = await authed_client.put(
            f"/api/v1/users/{target_id}/password",
            json={"password": "new-strong-password"},
            headers=_ROOT_HEADERS,
        )
        assert response.status_code == 200
        body = response.json()
        # The response must be a UserResponse — never expose the hash
        for field in ("id", "username", "role", "is_active"):
            assert field in body
        assert "password_hash" not in body
        assert "password" not in body

    @pytest.mark.asyncio
    async def test_non_root_returns_403(self, authed_client: httpx.AsyncClient) -> None:
        """A standard user cannot reset passwords → 403."""
        CONTEXT.auth_service.resolve_principal = AsyncMock(return_value=_USER_PRINCIPAL)

        response = await authed_client.put(
            f"/api/v1/users/{uuid.uuid4()}/password",
            json={"password": "new-password"},
            headers={"Authorization": "Bearer user-token"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_unknown_user_returns_404(self, authed_client: httpx.AsyncClient) -> None:
        """Resetting the password of a non-existent user → 404."""
        CONTEXT.user_repo.update_password = AsyncMock(return_value=None)

        response = await authed_client.put(
            f"/api/v1/users/{uuid.uuid4()}/password",
            json={"password": "new-password"},
            headers=_ROOT_HEADERS,
        )
        assert response.status_code == 404


# ── 13. GET /collections/{id}/access — list grants ───────────────────────────

class TestAccessRouterList:
    """
    GET /collections/{collection_id}/access — list collaborators.

    The access router is gated at the router level by require_collection_role(ADMIN).
    Non-admin callers are blocked before the handler even runs.
    """

    def _make_grant_orm(self, user_id: uuid.UUID) -> MagicMock:
        """Build a minimal grant ORM row for testing."""
        import datetime
        g = MagicMock()
        g.user_id = user_id
        g.role = "read"
        g.granted_by = _ROOT_USER_ID
        g.created_at = datetime.datetime.now()
        return g

    @pytest.mark.asyncio
    async def test_admin_can_list_access(self, authed_client: httpx.AsyncClient) -> None:
        """Admin/root can list the collection's collaborators → 200."""
        col_id = uuid.uuid4()
        user_id = uuid.uuid4()
        # collection must exist
        mock_col = MagicMock()
        mock_col.id = col_id
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=mock_col)
        # one grant in the list
        CONTEXT.grant_repo.list_for_collection = AsyncMock(
            return_value=[self._make_grant_orm(user_id)]
        )
        # user_repo.get_by_id resolves the username
        mock_user = MagicMock()
        mock_user.username = "alice"
        CONTEXT.user_repo.get_by_id = AsyncMock(return_value=mock_user)

        response = await authed_client.get(
            f"/api/v1/collections/{col_id}/access",
            headers=_ROOT_HEADERS,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["grants"][0]["role"] == "read"

    @pytest.mark.asyncio
    async def test_non_admin_returns_403(self, authed_client: httpx.AsyncClient) -> None:
        """A user with only READ on the collection cannot manage access → 403."""
        CONTEXT.auth_service.resolve_principal = AsyncMock(return_value=_USER_PRINCIPAL)
        # READ is below the ADMIN threshold required by the access router
        CONTEXT.auth_service.effective_collection_role = AsyncMock(return_value=GrantRole.READ)

        col_id = uuid.uuid4()
        response = await authed_client.get(
            f"/api/v1/collections/{col_id}/access",
            headers={"Authorization": "Bearer user-token"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_unknown_collection_returns_404(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """Admin requesting access list for a non-existent collection → 404."""
        col_id = uuid.uuid4()
        # Admin gate passes; collection_repo returns None (not found)
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=None)

        response = await authed_client.get(
            f"/api/v1/collections/{col_id}/access",
            headers=_ROOT_HEADERS,
        )
        assert response.status_code == 404


# ── 14. PUT /collections/{id}/access/{user_id} — set role ────────────────────

class TestAccessRouterSetRole:
    """
    PUT /collections/{collection_id}/access/{user_id} — grant or update a user's role.

    The PUT body must carry a valid ``role`` literal; anything else → 422 from Pydantic.
    """

    def _setup_set_access(
        self,
        col_id: uuid.UUID,
        target_id: uuid.UUID,
        role: str = "write",
    ) -> None:
        """Wire collection + user + grant mocks for a successful set-access call."""
        import datetime
        mock_col = MagicMock()
        mock_col.id = col_id
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=mock_col)
        mock_target = MagicMock()
        mock_target.id = target_id
        mock_target.username = "alice"
        CONTEXT.user_repo.get_by_id = AsyncMock(return_value=mock_target)
        mock_grant = MagicMock()
        mock_grant.user_id = target_id
        mock_grant.role = role
        mock_grant.granted_by = _ROOT_USER_ID
        mock_grant.created_at = datetime.datetime.now()
        CONTEXT.grant_repo.upsert = AsyncMock(return_value=mock_grant)

    @pytest.mark.asyncio
    async def test_admin_sets_role_returns_200(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """Admin/root grants write to a user → 200 with the updated grant."""
        col_id = uuid.uuid4()
        target_id = uuid.uuid4()
        self._setup_set_access(col_id, target_id, role="write")

        response = await authed_client.put(
            f"/api/v1/collections/{col_id}/access/{target_id}",
            json={"role": "write"},
            headers=_ROOT_HEADERS,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["role"] == "write"
        assert body["user_id"] == str(target_id)

    @pytest.mark.asyncio
    async def test_invalid_role_value_returns_422(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """A role value outside the allowed Literal set → 422 from Pydantic validation."""
        col_id = uuid.uuid4()
        target_id = uuid.uuid4()

        response = await authed_client.put(
            f"/api/v1/collections/{col_id}/access/{target_id}",
            json={"role": "superadmin"},  # not a valid Literal
            headers=_ROOT_HEADERS,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_non_admin_returns_403(self, authed_client: httpx.AsyncClient) -> None:
        """A non-admin user cannot set collection access → 403."""
        CONTEXT.auth_service.resolve_principal = AsyncMock(return_value=_USER_PRINCIPAL)
        CONTEXT.auth_service.effective_collection_role = AsyncMock(return_value=GrantRole.WRITE)

        col_id = uuid.uuid4()
        target_id = uuid.uuid4()
        response = await authed_client.put(
            f"/api/v1/collections/{col_id}/access/{target_id}",
            json={"role": "read"},
            headers={"Authorization": "Bearer user-token"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_unknown_user_returns_404(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """Granting access to a non-existent user id → 404."""
        col_id = uuid.uuid4()
        target_id = uuid.uuid4()
        mock_col = MagicMock()
        mock_col.id = col_id
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=mock_col)
        # user_repo returns None → 404
        CONTEXT.user_repo.get_by_id = AsyncMock(return_value=None)

        response = await authed_client.put(
            f"/api/v1/collections/{col_id}/access/{target_id}",
            json={"role": "read"},
            headers=_ROOT_HEADERS,
        )
        assert response.status_code == 404


# ── 15. DELETE /collections/{id}/access/{user_id} — revoke grant ─────────────

class TestAccessRouterRevokeGrant:
    """
    DELETE /collections/{collection_id}/access/{user_id} — remove a user's grant.
    """

    @pytest.mark.asyncio
    async def test_admin_revokes_grant_returns_200(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """Admin/root successfully revokes a user's grant → 200 with revoked=true."""
        col_id = uuid.uuid4()
        target_id = uuid.uuid4()
        mock_col = MagicMock()
        mock_col.id = col_id
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=mock_col)
        CONTEXT.grant_repo.delete = AsyncMock(return_value=True)

        response = await authed_client.delete(
            f"/api/v1/collections/{col_id}/access/{target_id}",
            headers=_ROOT_HEADERS,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["revoked"] is True
        assert body["collection_id"] == str(col_id)
        assert body["user_id"] == str(target_id)

    @pytest.mark.asyncio
    async def test_non_admin_returns_403(self, authed_client: httpx.AsyncClient) -> None:
        """Non-admin cannot revoke access → 403."""
        CONTEXT.auth_service.resolve_principal = AsyncMock(return_value=_USER_PRINCIPAL)
        CONTEXT.auth_service.effective_collection_role = AsyncMock(return_value=GrantRole.READ)

        col_id = uuid.uuid4()
        response = await authed_client.delete(
            f"/api/v1/collections/{col_id}/access/{uuid.uuid4()}",
            headers={"Authorization": "Bearer user-token"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_no_grant_to_revoke_returns_404(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """Revoking a grant that doesn't exist → 404."""
        col_id = uuid.uuid4()
        target_id = uuid.uuid4()
        mock_col = MagicMock()
        mock_col.id = col_id
        CONTEXT.collection_repo.get_by_id = AsyncMock(return_value=mock_col)
        # delete() returns False when no grant was found
        CONTEXT.grant_repo.delete = AsyncMock(return_value=False)

        response = await authed_client.delete(
            f"/api/v1/collections/{col_id}/access/{target_id}",
            headers=_ROOT_HEADERS,
        )
        assert response.status_code == 404


# ── 16. GET /collections/list — per-principal filtering ──────────────────────

class TestCollectionListFiltering:
    """
    GET /collections/list is filtered server-side based on the principal's role.

    Root sees all collections; a standard user sees only collections they have grants on.
    """

    def _make_collection_orm(self, col_id: uuid.UUID) -> MagicMock:
        """Minimal mock collection ORM row."""
        import datetime
        col = MagicMock()
        col.id = col_id
        col.name = f"col-{col_id.hex[:8]}"
        col.pipeline_version = "v1"
        col.needs_reindex = False
        col.supported_formats = ["pdf"]
        col.max_file_size_bytes = 10_000_000
        col.locality_policy = "external_allowed"
        col.embedding_model = "BAAI/bge-m3"
        col.unknown_field_policy = "ignore"
        col.pipeline = {}
        col.metadata_fields = []
        col.created_at = datetime.datetime.now()
        col.max_in_flight = None
        return col

    @pytest.mark.asyncio
    async def test_root_sees_all_collections(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """Root principal sees every collection, not just those with grants."""
        col_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        CONTEXT.collection_repo.list_all = AsyncMock(
            return_value=[self._make_collection_orm(cid) for cid in col_ids]
        )
        # grant_repo must NOT be called for root (is_root=True skips the filter branch)
        CONTEXT.grant_repo.list_collection_ids_for_user = AsyncMock(return_value=[])

        response = await authed_client.get(
            "/api/v1/collections/list", headers=_ROOT_HEADERS
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        # grant_repo was NOT queried for root
        CONTEXT.grant_repo.list_collection_ids_for_user.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_user_sees_only_granted_collections(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """A standard user sees only the collections they hold a grant on."""
        CONTEXT.auth_service.resolve_principal = AsyncMock(return_value=_USER_PRINCIPAL)
        col_a, col_b, col_c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        CONTEXT.collection_repo.list_all = AsyncMock(
            return_value=[
                self._make_collection_orm(col_a),
                self._make_collection_orm(col_b),
                self._make_collection_orm(col_c),
            ]
        )
        # user only has a grant on col_a and col_c
        CONTEXT.grant_repo.list_collection_ids_for_user = AsyncMock(
            return_value=[col_a, col_c]
        )

        response = await authed_client.get(
            "/api/v1/collections/list",
            headers={"Authorization": "Bearer user-token"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        returned_ids = {c["id"] for c in body["collections"]}
        assert str(col_a) in returned_ids
        assert str(col_c) in returned_ids
        assert str(col_b) not in returned_ids

    @pytest.mark.asyncio
    async def test_user_with_no_grants_sees_empty_list(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """A user with no grants gets an empty list (not 403 — the route is not blocked)."""
        CONTEXT.auth_service.resolve_principal = AsyncMock(return_value=_USER_PRINCIPAL)
        CONTEXT.collection_repo.list_all = AsyncMock(
            return_value=[self._make_collection_orm(uuid.uuid4())]
        )
        CONTEXT.grant_repo.list_collection_ids_for_user = AsyncMock(return_value=[])

        response = await authed_client.get(
            "/api/v1/collections/list",
            headers={"Authorization": "Bearer user-token"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 0


# ── 17. POST /collections/create — creator admin grant ───────────────────────

class TestCollectionCreateCreatorGrant:
    """
    POST /collections/create: a non-root creator receives an ADMIN grant on the new collection.

    Root callers skip the grant (root is implicitly admin on everything — recording a DB row
    would be redundant; the source code guards this with ``if not principal.is_root``).
    """

    def _make_collection_orm(self, col_id: uuid.UUID) -> MagicMock:
        """Minimal mock collection ORM row for create responses."""
        import datetime
        col = MagicMock()
        col.id = col_id
        col.name = "my-collection"
        col.pipeline_version = "v1"
        col.needs_reindex = False
        col.supported_formats = ["pdf"]
        col.max_file_size_bytes = 10_000_000
        col.locality_policy = "external_allowed"
        col.embedding_model = "BAAI/bge-m3"
        col.unknown_field_policy = "ignore"
        col.pipeline = {}
        col.metadata_fields = []
        col.created_at = datetime.datetime.now()
        col.max_in_flight = None
        return col

    @pytest.mark.asyncio
    async def test_non_root_creator_receives_admin_grant(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """Creating a collection as a non-root user → grant_repo.upsert called with ADMIN."""
        CONTEXT.auth_service.resolve_principal = AsyncMock(return_value=_USER_PRINCIPAL)
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.create = AsyncMock(
            return_value=self._make_collection_orm(col_id)
        )
        CONTEXT.grant_repo.upsert = AsyncMock()

        response = await authed_client.post(
            "/api/v1/collections/create",
            json={"name": "my-collection", "supported_formats": ["pdf"]},
            headers={"Authorization": "Bearer user-token"},
        )
        assert response.status_code == 201
        # grant_repo.upsert must have been called with ADMIN role for the creator
        CONTEXT.grant_repo.upsert.assert_awaited_once()
        call_kwargs = CONTEXT.grant_repo.upsert.call_args.kwargs
        assert call_kwargs["user_id"] == _USER_ID
        assert call_kwargs["collection_id"] == col_id
        assert call_kwargs["role"] == GrantRole.ADMIN.value

    @pytest.mark.asyncio
    async def test_root_creator_skips_grant(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """Creating a collection as root → grant_repo.upsert NOT called (root needs no grant)."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.create = AsyncMock(
            return_value=self._make_collection_orm(col_id)
        )
        CONTEXT.grant_repo.upsert = AsyncMock()

        response = await authed_client.post(
            "/api/v1/collections/create",
            json={"name": "root-collection", "supported_formats": ["pdf"]},
            headers=_ROOT_HEADERS,
        )
        assert response.status_code == 201
        # Root callers must NOT trigger a grant upsert
        CONTEXT.grant_repo.upsert.assert_not_awaited()


# ── 18. DB API-key auth through the HTTP boundary ────────────────────────────

class TestDbApiKeyAuthBoundary:
    """
    Verify that a DB API key (bearer resolved via get_by_hash + touch_last_used) is accepted
    at the HTTP boundary with AUTH_ENABLED=True.

    Instead of wiring the real AuthService, we program the mock ``resolve_principal`` to
    simulate what AuthService does when a valid DB key is presented: it returns a principal,
    and the route handler proceeds normally.  This tests the end-to-end HTTP gate — the internal
    AuthService resolution chain is unit-tested in test_auth_service.py.
    """

    @pytest.mark.asyncio
    async def test_db_api_key_bearer_accepted(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """A bearer token that resolves to a DB API key principal → 200 on a protected route."""
        _db_key_bearer = "docforge_testdbkey123"
        _db_key_principal = Principal(
            user_id=_USER_ID,
            username="alice",
            global_role=UserRole.USER,
            is_root=False,
        )

        # Simulate AuthService resolving a DB API key bearer
        async def _resolve(bearer: str | None) -> Principal | None:
            if bearer == _db_key_bearer:
                return _db_key_principal
            return None

        CONTEXT.auth_service.resolve_principal = AsyncMock(side_effect=_resolve)
        CONTEXT.grant_repo.list_collection_ids_for_user = AsyncMock(return_value=[])

        response = await authed_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {_db_key_bearer}"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["user"]["username"] == "alice"

    @pytest.mark.asyncio
    async def test_unresolvable_bearer_returns_401(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """A bearer that doesn't match any root key, JWT, or DB key → 401."""
        CONTEXT.auth_service.resolve_principal = AsyncMock(return_value=None)

        response = await authed_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer completely-invalid-token"},
        )
        assert response.status_code == 401


# ── 19. SSE ?token= auth ──────────────────────────────────────────────────────

class TestSseTokenAuth:
    """
    SSE routes use ``require_principal_sse`` which accepts auth from EITHER the
    Authorization header OR the ``?token=`` query parameter (EventSource-friendly).

    ``require_principal`` (non-SSE routes) must NOT accept the query parameter.

    Implementation note: ``SseHelpers.stream`` is patched to return an empty
    ``EventSourceResponse`` directly, because the full path (broadcaster.subscribe →
    asyncio.Queue.get) requires a running event loop with real queue writes. The patch
    lets us verify that auth passed (no 401/403) without spinning up the actual stream.
    """

    @staticmethod
    def _patch_sse_stream(monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Patch SseHelpers.stream to return an empty SSE response without a real broadcaster.

        Two patches are required:
          1. Inject a MagicMock for CONTEXT.event_broadcaster — the monitoring route reads it
             before calling SseHelpers.stream, so the attribute must exist in CONTEXT.
          2. Patch SseHelpers.stream on the module already imported by the monitoring router
             (``backend.routers.monitoring.router.SseHelpers``) so the fake is used when the
             router function calls ``SseHelpers.stream(CONTEXT.event_broadcaster, ...)``.
        """
        from sse_starlette.sse import EventSourceResponse

        # 1. Give CONTEXT an event_broadcaster so the route doesn't raise AttributeError
        monkeypatch.setattr(CONTEXT, "event_broadcaster", MagicMock(), raising=False)

        # 2. Patch the SseHelpers class reference already bound in the monitoring router
        async def _empty_gen():
            # Immediately-exhausted generator → empty SSE stream with HTTP 200
            return
            yield  # type: ignore[misc]

        def _fake_stream(broadcaster, *, keepalive, predicate=None):  # noqa: ANN001
            return EventSourceResponse(_empty_gen(), ping=keepalive)

        import importlib
        _mon_router_mod = importlib.import_module("backend.routers.monitoring.router")
        monkeypatch.setattr(
            _mon_router_mod.SseHelpers,
            "stream",
            staticmethod(_fake_stream),
            raising=True,
        )

    @pytest.mark.asyncio
    async def test_sse_header_auth_accepted(
        self, authed_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        GET /monitoring/stream with Authorization: Bearer header → 200 (stream opened).

        Auth passes the dependency; the route handler returns an SSE response.
        We only assert on the status code — the body is an empty stream.
        """
        self._patch_sse_stream(monkeypatch)
        # Provide a keepalive-seconds value so SseHelpers.stream receives a concrete int
        monkeypatch.setattr(CONTEXT.RUNTIME_CONFIG, "SSE_KEEPALIVE_SECONDS", 15, raising=False)

        response = await authed_client.get(
            "/api/v1/monitoring/stream",
            headers=_ROOT_HEADERS,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_sse_query_token_auth_accepted(
        self, authed_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        GET /monitoring/stream with ?token=<root-key> and NO Authorization header → 200.

        This is the EventSource browser path — the query parameter is the only credential.
        require_principal_sse accepts it as a fallback for header-less EventSource requests.
        """
        self._patch_sse_stream(monkeypatch)
        monkeypatch.setattr(CONTEXT.RUNTIME_CONFIG, "SSE_KEEPALIVE_SECONDS", 15, raising=False)

        response = await authed_client.get(
            f"/api/v1/monitoring/stream?token={_ROOT_API_KEY}",
            # No Authorization header — proves the query parameter path works alone
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
        """
        Regular (non-SSE) routes use ``require_principal``, which reads the header ONLY.

        Passing ?token=<root-key> without an Authorization header must produce 401 —
        the query parameter is intentionally rejected on non-SSE routes.
        """
        response = await authed_client.get(
            f"/api/v1/auth/me?token={_ROOT_API_KEY}",
        )
        assert response.status_code == 401


# ── 20. POST /users/{id}/impersonate — root act-as ───────────────────────────

class TestImpersonateUser:
    """
    POST /api/v1/users/{user_id}/impersonate — root mints a session AS another user.

    Behaviour:
      - Root impersonating a known active user → 200 with access_token + the target user.
      - Non-root caller → 403 (require_root gate).
      - Unknown user id → 404.
      - Inactive (deactivated) user → 409.
      - The minted token's principal IS the target user: creating an API key under it
        creates a key OWNED by the target, never the impersonating root.
    """

    def _make_user_orm(
        self,
        user_id: uuid.UUID,
        *,
        is_active: bool = True,
        role: str = "user",
        username: str = "bob",
    ) -> MagicMock:
        """Minimal mock user ORM row for impersonation tests."""
        import datetime
        user = MagicMock()
        user.id = user_id
        user.username = username
        user.role = role
        user.is_active = is_active
        user.created_at = datetime.datetime.now()
        return user

    @pytest.mark.asyncio
    async def test_root_impersonates_active_user_returns_200(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """Root impersonating a known active user → 200 with a login-shaped session."""
        target_id = uuid.uuid4()
        CONTEXT.user_repo.get_by_id = AsyncMock(return_value=self._make_user_orm(target_id))
        CONTEXT.auth_service.mint_impersonation_token = MagicMock(return_value="imp-jwt-token")

        response = await authed_client.post(
            f"/api/v1/users/{target_id}/impersonate", headers=_ROOT_HEADERS
        )
        assert response.status_code == 200
        body = response.json()
        assert body["access_token"] == "imp-jwt-token"
        assert body["token_type"] == "bearer"
        assert body["user"]["id"] == str(target_id)

    @pytest.mark.asyncio
    async def test_mint_called_with_root_as_impersonator(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """The token is minted for the target user, tagged with the calling root's id."""
        target_id = uuid.uuid4()
        CONTEXT.user_repo.get_by_id = AsyncMock(return_value=self._make_user_orm(target_id))
        CONTEXT.auth_service.mint_impersonation_token = MagicMock(return_value="imp-jwt-token")

        await authed_client.post(
            f"/api/v1/users/{target_id}/impersonate", headers=_ROOT_HEADERS
        )

        CONTEXT.auth_service.mint_impersonation_token.assert_called_once()
        kwargs = CONTEXT.auth_service.mint_impersonation_token.call_args.kwargs
        assert kwargs["impersonator_id"] == _ROOT_USER_ID
        assert kwargs["target"].user_id == target_id

    @pytest.mark.asyncio
    async def test_non_root_returns_403(self, authed_client: httpx.AsyncClient) -> None:
        """A standard user cannot impersonate anyone → 403 (require_root gate)."""
        CONTEXT.auth_service.resolve_principal = AsyncMock(return_value=_USER_PRINCIPAL)
        response = await authed_client.post(
            f"/api/v1/users/{uuid.uuid4()}/impersonate",
            headers={"Authorization": "Bearer user-token"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_unknown_user_returns_404(self, authed_client: httpx.AsyncClient) -> None:
        """Impersonating a user id that does not exist → 404."""
        CONTEXT.user_repo.get_by_id = AsyncMock(return_value=None)
        response = await authed_client.post(
            f"/api/v1/users/{uuid.uuid4()}/impersonate", headers=_ROOT_HEADERS
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_inactive_user_returns_409(self, authed_client: httpx.AsyncClient) -> None:
        """Impersonating a deactivated account → 409 (its session could never authenticate)."""
        target_id = uuid.uuid4()
        CONTEXT.user_repo.get_by_id = AsyncMock(
            return_value=self._make_user_orm(target_id, is_active=False)
        )
        response = await authed_client.post(
            f"/api/v1/users/{target_id}/impersonate", headers=_ROOT_HEADERS
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_api_key_under_impersonation_owned_by_target(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """
        A key created under the impersonation token is owned by the TARGET, not the root.

        The impersonation token resolves to the target principal (subject = target id, carrying
        ``impersonated_by`` = root id) — exactly what AuthService.mint_impersonation_token produces.
        The /auth/keys handler binds the new key to ``principal.user_id``, so it must be the target.
        """
        import datetime
        target_id = uuid.uuid4()
        imp_token = "impersonation-jwt-for-bob"
        target_principal = Principal(
            user_id=target_id,
            username="bob",
            global_role=UserRole.USER,
            is_root=False,
            impersonated_by=_ROOT_USER_ID,
        )

        async def _resolve(bearer: str | None) -> Principal | None:
            return target_principal if bearer == imp_token else None

        CONTEXT.auth_service.resolve_principal = AsyncMock(side_effect=_resolve)
        CONTEXT.auth_service.generate_api_key = MagicMock(
            return_value=("plaintext", "hash", "plaintex")
        )
        mock_key_orm = MagicMock()
        mock_key_orm.id = uuid.uuid4()
        mock_key_orm.name = "bobs-key"
        mock_key_orm.prefix = "plaintex"
        mock_key_orm.created_at = datetime.datetime.now()
        CONTEXT.api_key_repo.create = AsyncMock(return_value=mock_key_orm)

        response = await authed_client.post(
            "/api/v1/auth/keys",
            json={"name": "bobs-key"},
            headers={"Authorization": f"Bearer {imp_token}"},
        )
        assert response.status_code == 201

        # The key must be created OWNED by the target user, never the impersonating root.
        CONTEXT.api_key_repo.create.assert_awaited_once()
        create_kwargs = CONTEXT.api_key_repo.create.call_args.kwargs
        assert create_kwargs["user_id"] == target_id
        assert create_kwargs["user_id"] != _ROOT_USER_ID

    @pytest.mark.asyncio
    async def test_me_under_impersonation_surfaces_impersonated_by(
        self, authed_client: httpx.AsyncClient
    ) -> None:
        """GET /auth/me under an impersonation token exposes impersonated_by = the root's id."""
        imp_token = "impersonation-jwt-for-bob"
        target_principal = Principal(
            user_id=_USER_ID,
            username="bob",
            global_role=UserRole.USER,
            is_root=False,
            impersonated_by=_ROOT_USER_ID,
        )

        async def _resolve(bearer: str | None) -> Principal | None:
            return target_principal if bearer == imp_token else None

        CONTEXT.auth_service.resolve_principal = AsyncMock(side_effect=_resolve)
        CONTEXT.grant_repo.list_collection_ids_for_user = AsyncMock(return_value=[])

        response = await authed_client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {imp_token}"}
        )
        assert response.status_code == 200
        assert response.json()["impersonated_by"] == str(_ROOT_USER_ID)
