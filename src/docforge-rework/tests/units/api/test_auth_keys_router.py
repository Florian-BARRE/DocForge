"""The keys-management router (`/api/v1/auth/keys`) — create/list/revoke/rotate against the REAL app
via TestClient, auth forced ON (overriding the autouse off-by-default fixture). `authenticate`
resolves the caller through `CONTEXT.database.auth.get_key_with_user` (the AuthMiddleware authN
gate); the route handlers themselves are mocked on `CONTEXT.database.auth.{get_user_by_username,
create_key, list_keys, revoke_key}`. No live store — pattern mirrors test_enablement_routes.py
(per-method monkeypatch on the real CONTEXT.database.auth object) plus the auth-on setup from
test_auth.py."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT_ID = uuid.uuid4()


def _auth_on(monkeypatch) -> None:
    from config import RUNTIME_CONFIG

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)


def _root_principal_resolves(monkeypatch) -> None:
    """The bearer presented by every test resolves to a full-access (root) principal."""
    from backend.context import CONTEXT

    root_key = SimpleNamespace(
        id=uuid.uuid4(),
        permissions=None,
        revoked_at=None,
        user_id=ROOT_ID,
        expires_at=None,
        last_used_at=None,
    )
    root_user = SimpleNamespace(is_active=True)
    monkeypatch.setattr(
        CONTEXT.database.auth,
        "get_key_with_user",
        AsyncMock(return_value=(root_key, root_user)),
    )


def _scoped_non_admin_principal_resolves(monkeypatch) -> None:
    """The bearer resolves to a key scoped to everything EXCEPT the admin capability."""
    from backend.context import CONTEXT

    scoped_key = SimpleNamespace(
        id=uuid.uuid4(),
        permissions={"capabilities": ["read", "write"], "collections": ["*"]},
        revoked_at=None,
        user_id=uuid.uuid4(),
        expires_at=None,
        last_used_at=None,
    )
    user = SimpleNamespace(is_active=True)
    monkeypatch.setattr(
        CONTEXT.database.auth,
        "get_key_with_user",
        AsyncMock(return_value=(scoped_key, user)),
    )


def _headers() -> dict:
    return {"Authorization": "Bearer df_whatever"}


# ── POST /auth/keys ──────────────────────────────────────────────────────────────────────────


def test_create_key_returns_201_with_plaintext_present_once(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    _auth_on(monkeypatch)
    _root_principal_resolves(monkeypatch)
    monkeypatch.setattr(
        CONTEXT.database.auth,
        "get_user_by_username",
        AsyncMock(return_value=SimpleNamespace(id=ROOT_ID)),
    )
    created_id = uuid.uuid4()

    async def _create_key(key):
        return SimpleNamespace(
            id=created_id,
            name=key.name,
            prefix=key.prefix,
            permissions=key.permissions,
            created_at=datetime.now(UTC),
            expires_at=key.expires_at,
        )

    monkeypatch.setattr(CONTEXT.database.auth, "create_key", _create_key)

    response = client.post("/api/v1/auth/keys", json={"name": "ci-key"}, headers=_headers())

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] == str(created_id)
    assert body["name"] == "ci-key"
    assert isinstance(body["key"], str) and body["key"].startswith("df_")
    # The plaintext appears in exactly this one field of the response.
    assert sum(1 for v in body.values() if v == body["key"]) == 1


def test_create_key_root_not_provisioned_is_409(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    _auth_on(monkeypatch)
    _root_principal_resolves(monkeypatch)
    monkeypatch.setattr(CONTEXT.database.auth, "get_user_by_username", AsyncMock(return_value=None))

    response = client.post("/api/v1/auth/keys", json={"name": "ci-key"}, headers=_headers())

    assert response.status_code == 409, response.text


def test_create_key_with_expires_at_persists_it(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    _auth_on(monkeypatch)
    _root_principal_resolves(monkeypatch)
    monkeypatch.setattr(
        CONTEXT.database.auth,
        "get_user_by_username",
        AsyncMock(return_value=SimpleNamespace(id=ROOT_ID)),
    )
    created_id = uuid.uuid4()
    captured = {}

    async def _create_key(key):
        captured["expires_at"] = key.expires_at
        return SimpleNamespace(
            id=created_id,
            name=key.name,
            prefix=key.prefix,
            permissions=key.permissions,
            created_at=datetime.now(UTC),
            expires_at=key.expires_at,
        )

    monkeypatch.setattr(CONTEXT.database.auth, "create_key", _create_key)

    response = client.post(
        "/api/v1/auth/keys",
        json={"name": "ci-key", "expires_at": "2030-01-01T00:00:00Z"},
        headers=_headers(),
    )

    assert response.status_code == 201, response.text
    assert captured["expires_at"] == datetime(2030, 1, 1, tzinfo=UTC)
    assert response.json()["expires_at"] is not None


def test_create_key_non_admin_scoped_key_is_403(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    _auth_on(monkeypatch)
    _scoped_non_admin_principal_resolves(monkeypatch)
    create_key = AsyncMock()
    monkeypatch.setattr(CONTEXT.database.auth, "create_key", create_key)

    response = client.post("/api/v1/auth/keys", json={"name": "ci-key"}, headers=_headers())

    assert response.status_code == 403, response.text
    create_key.assert_not_called()


# ── GET /auth/keys ───────────────────────────────────────────────────────────────────────────


def test_list_keys_returns_200_without_secret_fields(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    _auth_on(monkeypatch)
    _root_principal_resolves(monkeypatch)
    monkeypatch.setattr(
        CONTEXT.database.auth,
        "get_user_by_username",
        AsyncMock(return_value=SimpleNamespace(id=ROOT_ID)),
    )
    rows = [
        SimpleNamespace(
            id=uuid.uuid4(),
            name="ci-key",
            key_hash="deadbeef" * 8,
            prefix="df_abcdefgh",
            permissions=None,
            created_at=datetime.now(UTC),
            expires_at=None,
            last_used_at=None,
            revoked_at=None,
        )
    ]
    monkeypatch.setattr(CONTEXT.database.auth, "list_keys", AsyncMock(return_value=rows))

    response = client.get("/api/v1/auth/keys", headers=_headers())

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    for row in body:
        assert "key" not in row
        assert "key_hash" not in row


def test_list_keys_surfaces_expiry_and_last_used(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    _auth_on(monkeypatch)
    _root_principal_resolves(monkeypatch)
    monkeypatch.setattr(
        CONTEXT.database.auth,
        "get_user_by_username",
        AsyncMock(return_value=SimpleNamespace(id=ROOT_ID)),
    )
    rows = [
        SimpleNamespace(
            id=uuid.uuid4(),
            name="ci-key",
            key_hash="deadbeef" * 8,
            prefix="df_abcdefgh",
            permissions=None,
            created_at=datetime.now(UTC),
            expires_at=datetime(2030, 1, 1, tzinfo=UTC),
            last_used_at=datetime(2026, 7, 1, tzinfo=UTC),
            revoked_at=None,
        )
    ]
    monkeypatch.setattr(CONTEXT.database.auth, "list_keys", AsyncMock(return_value=rows))

    response = client.get("/api/v1/auth/keys", headers=_headers())

    assert response.status_code == 200, response.text
    body = response.json()[0]
    assert body["expires_at"] == "2030-01-01T00:00:00Z"
    assert body["last_used_at"] == "2026-07-01T00:00:00Z"


def test_list_keys_non_admin_scoped_key_is_403(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    _auth_on(monkeypatch)
    _scoped_non_admin_principal_resolves(monkeypatch)
    list_keys = AsyncMock()
    monkeypatch.setattr(CONTEXT.database.auth, "list_keys", list_keys)

    response = client.get("/api/v1/auth/keys", headers=_headers())

    assert response.status_code == 403, response.text
    list_keys.assert_not_called()


# ── DELETE /auth/keys/{key_id} ───────────────────────────────────────────────────────────────


def test_revoke_key_returns_204(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    _auth_on(monkeypatch)
    _root_principal_resolves(monkeypatch)
    revoke_key = AsyncMock()
    monkeypatch.setattr(CONTEXT.database.auth, "revoke_key", revoke_key)

    response = client.delete(f"/api/v1/auth/keys/{uuid.uuid4()}", headers=_headers())

    assert response.status_code == 204, response.text
    assert response.content == b""
    revoke_key.assert_awaited_once()


def test_revoke_key_non_admin_scoped_key_is_403(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    _auth_on(monkeypatch)
    _scoped_non_admin_principal_resolves(monkeypatch)
    revoke_key = AsyncMock()
    monkeypatch.setattr(CONTEXT.database.auth, "revoke_key", revoke_key)

    response = client.delete(f"/api/v1/auth/keys/{uuid.uuid4()}", headers=_headers())

    assert response.status_code == 403, response.text
    revoke_key.assert_not_called()


# ── POST /auth/keys/{key_id}/rotate ─────────────────────────────────────────────────────────


def _old_key(
    *,
    key_id=None,
    user_id=ROOT_ID,
    name="old-name",
    permissions=None,
    expires_at=None,
    revoked_at=None,
) -> SimpleNamespace:
    """A stand-in for the source ApiKey row being rotated (only the fields the handler reads)."""
    return SimpleNamespace(
        id=key_id or uuid.uuid4(),
        user_id=user_id,
        name=name,
        permissions=permissions,
        expires_at=expires_at,
        revoked_at=revoked_at,
    )


def _mock_rotate_create(monkeypatch, captured: dict) -> None:
    """Wire ``create_key`` to capture the ApiKey row the router builds for the replacement key."""
    from backend.context import CONTEXT

    async def _create_key(key):
        captured["key"] = key
        return SimpleNamespace(
            id=uuid.uuid4(),
            name=key.name,
            prefix=key.prefix,
            permissions=key.permissions,
            created_at=datetime.now(UTC),
            expires_at=key.expires_at,
        )

    monkeypatch.setattr(CONTEXT.database.auth, "create_key", _create_key)


def test_rotate_key_happy_path_clones_and_revokes_old(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    _auth_on(monkeypatch)
    _root_principal_resolves(monkeypatch)
    monkeypatch.setattr(
        CONTEXT.database.auth,
        "get_user_by_username",
        AsyncMock(return_value=SimpleNamespace(id=ROOT_ID)),
    )
    old = _old_key(name="ci-key", permissions={"capabilities": ["read"], "collections": ["*"]})
    monkeypatch.setattr(CONTEXT.database.auth, "get_key", AsyncMock(return_value=old))
    captured: dict = {}
    _mock_rotate_create(monkeypatch, captured)
    revoke_key = AsyncMock()
    monkeypatch.setattr(CONTEXT.database.auth, "revoke_key", revoke_key)

    response = client.post(f"/api/v1/auth/keys/{old.id}/rotate", json={}, headers=_headers())

    assert response.status_code == 201, response.text
    body = response.json()
    assert isinstance(body["key"], str) and body["key"].startswith("df_")
    # Absent fields clone the source key verbatim.
    assert captured["key"].name == old.name
    assert captured["key"].permissions == old.permissions
    assert captured["key"].expires_at == old.expires_at
    # Exactly one active credential survives the rotation.
    revoke_key.assert_awaited_once()
    assert revoke_key.await_args.args[0] == old.id


def test_rotate_key_null_permissions_override_grants_full_access(client, monkeypatch) -> None:
    """A ``permissions: null`` field IS present in the payload — applied, not cloned from the scoped source."""
    from backend.context import CONTEXT

    _auth_on(monkeypatch)
    _root_principal_resolves(monkeypatch)
    monkeypatch.setattr(
        CONTEXT.database.auth,
        "get_user_by_username",
        AsyncMock(return_value=SimpleNamespace(id=ROOT_ID)),
    )
    old = _old_key(
        name="old-name",
        permissions={"capabilities": ["read"], "collections": ["*"]},
        expires_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    monkeypatch.setattr(CONTEXT.database.auth, "get_key", AsyncMock(return_value=old))
    captured: dict = {}
    _mock_rotate_create(monkeypatch, captured)
    monkeypatch.setattr(CONTEXT.database.auth, "revoke_key", AsyncMock())

    response = client.post(
        f"/api/v1/auth/keys/{old.id}/rotate",
        json={"permissions": None, "expires_at": "2031-01-01T00:00:00Z"},
        headers=_headers(),
    )

    assert response.status_code == 201, response.text
    assert captured["key"].permissions is None
    assert captured["key"].expires_at == datetime(2031, 1, 1, tzinfo=UTC)
    # name absent from the payload -> cloned from the source key.
    assert captured["key"].name == old.name


def test_rotate_key_scoped_permissions_override_replaces_full_access(client, monkeypatch) -> None:
    """A concrete scope IS provided — it replaces the source key's full-access (null) permissions."""
    from backend.context import CONTEXT

    _auth_on(monkeypatch)
    _root_principal_resolves(monkeypatch)
    monkeypatch.setattr(
        CONTEXT.database.auth,
        "get_user_by_username",
        AsyncMock(return_value=SimpleNamespace(id=ROOT_ID)),
    )
    old = _old_key(permissions=None)
    monkeypatch.setattr(CONTEXT.database.auth, "get_key", AsyncMock(return_value=old))
    captured: dict = {}
    _mock_rotate_create(monkeypatch, captured)
    monkeypatch.setattr(CONTEXT.database.auth, "revoke_key", AsyncMock())
    new_scope = {"capabilities": ["read"], "collections": ["*"]}

    response = client.post(
        f"/api/v1/auth/keys/{old.id}/rotate",
        json={"permissions": new_scope},
        headers=_headers(),
    )

    assert response.status_code == 201, response.text
    assert captured["key"].permissions == new_scope


def test_rotate_key_missing_key_is_404(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    _auth_on(monkeypatch)
    _root_principal_resolves(monkeypatch)
    monkeypatch.setattr(
        CONTEXT.database.auth,
        "get_user_by_username",
        AsyncMock(return_value=SimpleNamespace(id=ROOT_ID)),
    )
    monkeypatch.setattr(CONTEXT.database.auth, "get_key", AsyncMock(return_value=None))

    response = client.post(f"/api/v1/auth/keys/{uuid.uuid4()}/rotate", json={}, headers=_headers())

    assert response.status_code == 404, response.text


def test_rotate_key_not_owned_by_root_is_404(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    _auth_on(monkeypatch)
    _root_principal_resolves(monkeypatch)
    monkeypatch.setattr(
        CONTEXT.database.auth,
        "get_user_by_username",
        AsyncMock(return_value=SimpleNamespace(id=ROOT_ID)),
    )
    foreign_key = _old_key(user_id=uuid.uuid4())
    monkeypatch.setattr(CONTEXT.database.auth, "get_key", AsyncMock(return_value=foreign_key))

    response = client.post(
        f"/api/v1/auth/keys/{foreign_key.id}/rotate", json={}, headers=_headers()
    )

    assert response.status_code == 404, response.text


def test_rotate_key_already_revoked_is_409(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    _auth_on(monkeypatch)
    _root_principal_resolves(monkeypatch)
    monkeypatch.setattr(
        CONTEXT.database.auth,
        "get_user_by_username",
        AsyncMock(return_value=SimpleNamespace(id=ROOT_ID)),
    )
    revoked = _old_key(revoked_at=datetime.now(UTC))
    monkeypatch.setattr(CONTEXT.database.auth, "get_key", AsyncMock(return_value=revoked))

    response = client.post(f"/api/v1/auth/keys/{revoked.id}/rotate", json={}, headers=_headers())

    assert response.status_code == 409, response.text
