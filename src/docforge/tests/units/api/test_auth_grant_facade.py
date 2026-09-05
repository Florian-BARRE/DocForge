"""AuthFacade.grant_collection_to_key — the reusable creator-ownership step shared by the normal
create path and the async collection import. Postgres fully mocked (pattern from
test_filter_sync_facade.py): the test proves WHAT the façade reads and WHETHER it persists, never a
real store. It appends + persists for a list-scoped key, and no-ops (returns False, zero write) on a
wildcard scope, a duplicate id, a full-access (NULL-permission) key, and an absent key.
"""

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from shared_libs.services.db.facades import AuthFacade
from shared_libs.services.db.facades import auth_facade as af_module


def _postgres_yielding(session: MagicMock) -> MagicMock:
    """A postgres mock whose session() is an async context manager yielding ``session``."""

    @asynccontextmanager
    async def _session():
        yield session

    postgres = MagicMock()
    postgres.session = _session
    return postgres


def _facade_with_key(monkeypatch, key) -> tuple[AuthFacade, AsyncMock]:
    """An AuthFacade whose AuthApi.get_key returns ``key`` and whose update is a recording spy."""
    update = AsyncMock()
    monkeypatch.setattr(af_module.AuthApi, "get_key", AsyncMock(return_value=key))
    monkeypatch.setattr(af_module.AuthApi, "update_key_permissions", update)
    return AuthFacade(_postgres_yielding(MagicMock())), update


async def test_grant_appends_and_persists_for_list_scoped_key(monkeypatch) -> None:
    key_id, collection_id = uuid.uuid4(), str(uuid.uuid4())
    key = SimpleNamespace(permissions={"capabilities": ["create"], "collections": []})
    facade, update = _facade_with_key(monkeypatch, key)

    granted = await facade.grant_collection_to_key(key_id, collection_id)

    assert granted is True
    update.assert_awaited_once()
    # AuthApi.update_key_permissions(session, key_id, permissions) — the new id is in the scope.
    _session, persisted_key_id, persisted = update.await_args.args
    assert persisted_key_id == key_id
    assert collection_id in persisted["collections"]


async def test_grant_noop_on_wildcard_scope(monkeypatch) -> None:
    key = SimpleNamespace(permissions={"capabilities": ["create"], "collections": ["*"]})
    facade, update = _facade_with_key(monkeypatch, key)

    granted = await facade.grant_collection_to_key(uuid.uuid4(), str(uuid.uuid4()))

    assert granted is False
    update.assert_not_awaited()


async def test_grant_noop_on_duplicate_id(monkeypatch) -> None:
    collection_id = str(uuid.uuid4())
    key = SimpleNamespace(permissions={"capabilities": ["create"], "collections": [collection_id]})
    facade, update = _facade_with_key(monkeypatch, key)

    granted = await facade.grant_collection_to_key(uuid.uuid4(), collection_id)

    assert granted is False
    update.assert_not_awaited()


async def test_grant_noop_on_full_access_key(monkeypatch) -> None:
    key = SimpleNamespace(permissions=None)
    facade, update = _facade_with_key(monkeypatch, key)

    granted = await facade.grant_collection_to_key(uuid.uuid4(), str(uuid.uuid4()))

    assert granted is False
    update.assert_not_awaited()


async def test_grant_noop_on_absent_key(monkeypatch) -> None:
    facade, update = _facade_with_key(monkeypatch, None)

    granted = await facade.grant_collection_to_key(uuid.uuid4(), str(uuid.uuid4()))

    assert granted is False
    update.assert_not_awaited()
