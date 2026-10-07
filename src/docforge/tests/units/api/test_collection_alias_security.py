"""Collection-alias authorization ratchets (the pre-0.29 review findings).

* alias writes are full-access only — a scoped admin re-pointing an alias would re-scope every key
  bound to it, including keys it could never manage (H1);
* an alias named by live keys cannot be deleted — a freed name would re-bind those keys to whoever
  re-creates it (H2);
* a scoped caller grants only what it STORES — never an alias's current target as a pinned UUID (M1);
* an alias outside the caller's scope answers the same 404 as an unknown one, never a 403 naming its
  target id, and a key lacking the route's capability never reaches the alias lookup (M2).
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from test_collection_aliases import HEADERS, A, B, _alias_store, _live_targets

ALIAS_URL = "/api/v1/collection-aliases/chatmop"


def _scoped(monkeypatch, capabilities: list[str], collections: list[str]) -> None:
    """Auth ON with ONE scoped key (cache bypassed so every request re-authenticates)."""
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.libs.auth.dependency import _KEY_CACHE  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)
    key = SimpleNamespace(
        id=uuid.uuid4(),
        permissions={"capabilities": capabilities, "collections": collections},
        revoked_at=None,
        user_id=uuid.uuid4(),
        expires_at=None,
        last_used_at=None,
    )
    auth = CONTEXT.database.auth
    monkeypatch.setattr(
        auth, "get_key_with_user", AsyncMock(return_value=(key, SimpleNamespace(is_active=True)))
    )
    monkeypatch.setattr(auth, "touch_key_last_used", AsyncMock())
    monkeypatch.setattr(_KEY_CACHE, "get", lambda _hash: (False, None))


def test_scoped_admin_cannot_write_an_alias(client, monkeypatch) -> None:
    _live_targets(monkeypatch, {})
    _scoped(monkeypatch, ["admin", "read_text"], [str(A), str(B)])
    store = AsyncMock()
    _alias_store(monkeypatch, set=store, delete=store)

    put = client.put(ALIAS_URL, json={"collection_id": str(B)}, headers=HEADERS)
    delete = client.delete(ALIAS_URL, headers=HEADERS)

    assert put.status_code == 403 and delete.status_code == 403
    store.assert_not_awaited()


def test_delete_of_an_alias_named_by_live_keys_is_a_409(client, monkeypatch) -> None:
    from shared_libs.services.db.facades import CollectionAliasInUseError  # noqa: PLC0415

    _alias_store(monkeypatch, delete=AsyncMock(side_effect=CollectionAliasInUseError("chatmop", 2)))

    response = client.delete(ALIAS_URL)

    assert response.status_code == 409
    assert "alias:chatmop" in response.text


def test_out_of_scope_alias_is_an_indistinguishable_404(client, monkeypatch) -> None:
    _live_targets(monkeypatch, {"mine": A, "tenant-b": B})
    _scoped(monkeypatch, ["read_text"], ["alias:mine"])

    foreign = client.get("/api/v1/collections/tenant-b", headers=HEADERS)
    unknown = client.get("/api/v1/collections/nope", headers=HEADERS)

    assert foreign.status_code == unknown.status_code == 404
    assert str(B) not in foreign.text


def test_a_key_lacking_the_capability_cannot_probe_alias_existence(client, monkeypatch) -> None:
    _live_targets(monkeypatch, {"tenant-b": B})
    _scoped(monkeypatch, ["search"], ["*"])

    existing = client.get("/api/v1/collections/tenant-b", headers=HEADERS)
    unknown = client.get("/api/v1/collections/nope", headers=HEADERS)

    assert existing.status_code == unknown.status_code == 403
    assert existing.json() == unknown.json()


def test_alias_only_caller_cannot_pin_the_alias_target_as_a_uuid(fastapi_app) -> None:
    from backend.libs.auth import AuthPrincipal  # noqa: PLC0415
    from backend.libs.auth.grant_guard import KeyGrantGuard  # noqa: PLC0415
    from backend.libs.auth.permissions import KeyPermissions  # noqa: PLC0415

    key = SimpleNamespace(permissions={"capabilities": ["admin"], "collections": ["alias:prod"]})
    caller = AuthPrincipal(user=None, key=key, is_full_access=False, alias_targets={"prod": str(A)})

    pinned = KeyPermissions.model_validate({"capabilities": ["admin"], "collections": [str(A)]})
    with pytest.raises(HTTPException) as refused:
        KeyGrantGuard.assert_can_grant(caller, pinned)
    assert refused.value.status_code == 403

    same_alias = KeyPermissions.model_validate(
        {"capabilities": ["admin"], "collections": ["alias:prod"]}
    )
    KeyGrantGuard.assert_can_grant(caller, same_alias)
