"""The keys-management router (`/api/v1/auth/keys`) — create/list/revoke against the REAL app
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

    root_key = SimpleNamespace(permissions=None, revoked_at=None, user_id=ROOT_ID)
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
        permissions={"capabilities": ["read", "write"], "collections": ["*"]},
        revoked_at=None,
        user_id=uuid.uuid4(),
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
        )

    monkeypatch.setattr(CONTEXT.database.auth, "create_key", _create_key)

    response = client.post(
        "/api/v1/auth/keys", json={"name": "ci-key"}, headers=_headers()
    )

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
    monkeypatch.setattr(
        CONTEXT.database.auth, "get_user_by_username", AsyncMock(return_value=None)
    )

    response = client.post(
        "/api/v1/auth/keys", json={"name": "ci-key"}, headers=_headers()
    )

    assert response.status_code == 409, response.text


def test_create_key_non_admin_scoped_key_is_403(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    _auth_on(monkeypatch)
    _scoped_non_admin_principal_resolves(monkeypatch)
    create_key = AsyncMock()
    monkeypatch.setattr(CONTEXT.database.auth, "create_key", create_key)

    response = client.post(
        "/api/v1/auth/keys", json={"name": "ci-key"}, headers=_headers()
    )

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
