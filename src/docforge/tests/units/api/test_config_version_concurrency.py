"""Config-version minting is concurrency-safe: two simultaneous config PATCHes on the SAME collection
mint DISTINCT, sequential versions — never a duplicate (collection_id, version) or a 500.

Before the fix, ``_apply_config`` read ``max(version)`` then wrote ``max + 1`` with nothing
serializing the pair, so two concurrent PATCHes both read N and both wrote N+1. The fix locks the
collection row ``FOR UPDATE`` (``CollectionApi.get_for_update``) before the read-modify-write, with a
``UNIQUE (collection_id, version)`` constraint as the DB backstop.

These tests are serviceless: a small in-memory fake models the two mechanics that matter — the
per-row FOR UPDATE lock (an ``asyncio.Lock`` released at transaction end) and the UNIQUE constraint
(a duplicate version raises ``IntegrityError``). The negative test proves the fake genuinely catches a
collision, so the positive test is not vacuous."""

import asyncio
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy.exc import IntegrityError

from shared_libs.services.db.facades import collections_facade as cf_module
from shared_libs.services.db.facades.collections_facade import CollectionsFacade


class _FakeConfigStore:
    """An in-memory config_version table modeling the FOR UPDATE lock + UNIQUE(collection_id, version)."""

    def __init__(self, initial_max: int) -> None:
        self._versions: list[int] = list(range(1, initial_max + 1))
        self._row_lock = asyncio.Lock()  # stands in for the collection-row FOR UPDATE lock
        self.integrity_errors = 0

    async def get_for_update(self, session, _collection_id):
        """Acquire the row lock and remember it on the session so it is released at transaction end."""
        await self._row_lock.acquire()
        session.held_lock = self._row_lock
        return SimpleNamespace(pipeline={}, search={})

    async def get_for_update_nolock(self, _session, _collection_id):
        """The pre-fix behavior: read the row WITHOUT locking it — lets the race interleave."""
        return SimpleNamespace(pipeline={}, search={})

    async def update(self, _session, _collection_id, **_kwargs):
        return None

    async def max_config_version(self, _session, _collection_id) -> int:
        await asyncio.sleep(0)  # a yield point where an unlocked race would interleave
        return max(self._versions, default=0)

    async def add_config_version(self, _session, version_obj):
        await asyncio.sleep(0)
        if version_obj.version in self._versions:
            self.integrity_errors += 1
            raise IntegrityError("insert", {}, Exception("uq_config_version_collection_id"))
        self._versions.append(version_obj.version)
        return version_obj

    @property
    def versions(self) -> list[int]:
        return self._versions


def _postgres(store: _FakeConfigStore) -> MagicMock:
    """A postgres mock whose session() releases any FOR UPDATE lock the session holds at exit."""

    @asynccontextmanager
    async def _session():
        session = SimpleNamespace(held_lock=None)
        try:
            yield session
        finally:
            lock = session.held_lock
            if lock is not None and lock.locked():
                lock.release()

    postgres = MagicMock()
    postgres.session = _session
    return postgres


def _wire(monkeypatch, store: _FakeConfigStore, *, lock: bool) -> None:
    getter = store.get_for_update if lock else store.get_for_update_nolock
    monkeypatch.setattr(cf_module.CollectionApi, "get_for_update", getter)
    monkeypatch.setattr(cf_module.CollectionApi, "update", store.update)
    monkeypatch.setattr(cf_module.CollectionApi, "max_config_version", store.max_config_version)
    monkeypatch.setattr(cf_module.CollectionApi, "add_config_version", store.add_config_version)


async def test_concurrent_config_updates_mint_distinct_sequential_versions(monkeypatch) -> None:
    """Two concurrent PATCHes serialize on the row lock → versions 4 and 5, no duplicate, no error."""
    store = _FakeConfigStore(initial_max=3)
    _wire(monkeypatch, store, lock=True)
    facade = CollectionsFacade(_postgres(store), MagicMock(), MagicMock())
    collection_id = uuid.uuid4()

    await asyncio.gather(
        facade.update_config(collection_id, pipeline={"a": 1}, note="one"),
        facade.update_config(collection_id, pipeline={"b": 2}, note="two"),
    )

    assert store.integrity_errors == 0
    assert sorted(store.versions) == [1, 2, 3, 4, 5]  # gap-free, no duplicate


async def test_without_the_row_lock_the_race_would_collide(monkeypatch) -> None:
    """Sanity check on the fake: WITHOUT the lock the two PATCHes both mint N+1 → a UNIQUE violation.
    This proves the store models the constraint, so the positive test above is meaningful."""
    store = _FakeConfigStore(initial_max=3)
    _wire(monkeypatch, store, lock=False)
    facade = CollectionsFacade(_postgres(store), MagicMock(), MagicMock())
    collection_id = uuid.uuid4()

    results = await asyncio.gather(
        facade.update_config(collection_id, pipeline={"a": 1}, note="one"),
        facade.update_config(collection_id, pipeline={"b": 2}, note="two"),
        return_exceptions=True,
    )

    assert store.integrity_errors == 1
    assert any(isinstance(r, IntegrityError) for r in results)
