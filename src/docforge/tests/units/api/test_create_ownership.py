"""Auto-ownership on collection creation: `CollectionStoreSync.grant_creator_scope` now delegates the
read → append-if-list-scoped-and-absent → persist logic to the store façade's
`grant_collection_to_key` (shared with the async import path). This test pins the APP-SIDE contract:
a full-access / keyless principal short-circuits (no façade call); any permissioned key delegates the
decision to the façade with `(key.id, collection_id)`. The wildcard / duplicate NO-OP itself lives in
the façade now and is covered in `test_auth_grant_facade.py`.

Exercises `CollectionStoreSync.grant_creator_scope` directly with an explicit principal + a mocked
auth facade — no store, no HTTP.
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

    grant = AsyncMock(return_value=True)
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(auth=SimpleNamespace(grant_collection_to_key=grant))
    )
    return grant


async def test_scoped_create_delegates_grant_to_facade(fastapi_app, monkeypatch) -> None:
    from backend.routers.collections.store_sync import CollectionStoreSync  # noqa: PLC0415

    grant = _mock_auth(monkeypatch)
    principal = _principal(
        permissions={"capabilities": ["read", "write", "create"], "collections": []}
    )

    await CollectionStoreSync.grant_creator_scope(principal, NEW_ID)

    # The app-side guard passes (permissioned key) → the append decision is delegated to the façade.
    grant.assert_awaited_once_with(principal.key.id, NEW_ID)


async def test_full_access_key_is_not_extended(fastapi_app, monkeypatch) -> None:
    from backend.routers.collections.store_sync import CollectionStoreSync  # noqa: PLC0415

    grant = _mock_auth(monkeypatch)
    await CollectionStoreSync.grant_creator_scope(_principal(permissions=None), NEW_ID)
    # A NULL-permission (full-access) key short-circuits app-side — the façade is never called.
    grant.assert_not_awaited()


async def test_wildcard_key_still_delegates_to_facade(fastapi_app, monkeypatch) -> None:
    from backend.routers.collections.store_sync import CollectionStoreSync  # noqa: PLC0415

    grant = _mock_auth(monkeypatch)
    principal = _principal(permissions={"capabilities": ["create"], "collections": ["*"]})

    await CollectionStoreSync.grant_creator_scope(principal, NEW_ID)

    # A wildcard scope is permissioned (not NULL), so the app still delegates; the actual no-op on a
    # wildcard scope is the façade's responsibility (see test_auth_grant_facade.py).
    grant.assert_awaited_once_with(principal.key.id, NEW_ID)
