"""Auto-ownership on collection creation: a scoped key holding CREATE that creates a collection has
the new id appended to its own `collections` scope (so it can then manage what it created), while a
full-access key and a wildcard-scoped key are left untouched.

Exercises `backend.routers.collections.router._grant_creator_scope` directly with an explicit
principal + a mocked auth facade — no store, no HTTP.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

NEW_ID = "33333333-3333-3333-3333-333333333333"


def _principal(*, permissions):
    from backend.libs.auth.principal import AuthPrincipal  # noqa: PLC0415

    key = SimpleNamespace(id=uuid.uuid4(), permissions=permissions)
    return AuthPrincipal(
        user=SimpleNamespace(is_active=True), key=key, is_full_access=permissions is None
    )


def _mock_auth(monkeypatch):
    from backend.context import CONTEXT  # noqa: PLC0415

    update = AsyncMock()
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(auth=SimpleNamespace(update_key_permissions=update))
    )
    return update


async def test_scoped_create_appends_new_collection_to_scope(fastapi_app, monkeypatch) -> None:
    from backend.routers.collections.store_sync import CollectionStoreSync  # noqa: PLC0415

    update = _mock_auth(monkeypatch)
    principal = _principal(
        permissions={"capabilities": ["read", "write", "create"], "collections": []}
    )

    await CollectionStoreSync.grant_creator_scope(principal, NEW_ID)

    update.assert_awaited_once()
    key_id, permissions = update.await_args.args
    assert key_id == principal.key.id
    assert NEW_ID in permissions["collections"]


async def test_full_access_key_is_not_extended(fastapi_app, monkeypatch) -> None:
    from backend.routers.collections.store_sync import CollectionStoreSync  # noqa: PLC0415

    update = _mock_auth(monkeypatch)
    await CollectionStoreSync.grant_creator_scope(_principal(permissions=None), NEW_ID)
    update.assert_not_awaited()


async def test_wildcard_scope_is_not_extended(fastapi_app, monkeypatch) -> None:
    from backend.routers.collections.store_sync import CollectionStoreSync  # noqa: PLC0415

    update = _mock_auth(monkeypatch)
    principal = _principal(permissions={"capabilities": ["create"], "collections": ["*"]})
    await CollectionStoreSync.grant_creator_scope(principal, NEW_ID)
    update.assert_not_awaited()


async def test_already_scoped_collection_is_not_duplicated(fastapi_app, monkeypatch) -> None:
    from backend.routers.collections.store_sync import CollectionStoreSync  # noqa: PLC0415

    update = _mock_auth(monkeypatch)
    principal = _principal(permissions={"capabilities": ["create"], "collections": [NEW_ID]})
    await CollectionStoreSync.grant_creator_scope(principal, NEW_ID)
    update.assert_not_awaited()
