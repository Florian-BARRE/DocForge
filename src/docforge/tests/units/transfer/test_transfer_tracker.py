"""TransferTrackerFacade — terminal-success write + the stuck-transfer reaper.

``mark_done`` pins that a completed IMPORT stamps BOTH the new collection's id AND its name onto the
tracking row, so a polled ``GET /transfers/{id}`` surfaces the real name instead of the null the UI
falls back to generic text for. ``reap_stale`` marks a RUNNING transfer whose ``updated_at`` froze
past the horizon as FAILED (recovering a row a worker hard-kill left RUNNING forever); the freshness
discrimination lives in ``TransferApi.list_stale``'s WHERE, asserted here on the compiled SQL.
Postgres is mocked (the same session-yielding stub the other facade tests use).
"""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from shared_libs.services.db.facades import TransferTrackerFacade
from shared_libs.services.db.facades import transfer_tracker_facade as facade_module
from shared_libs.services.db.postgresql.apis import TransferApi
from shared_libs.services.db.postgresql.tables import TransferStatus


def _postgres_yielding(session: MagicMock) -> MagicMock:
    """A postgres mock whose session() is an async context manager yielding ``session``."""

    @asynccontextmanager
    async def _session():
        yield session

    postgres = MagicMock()
    postgres.session = _session
    return postgres


async def test_mark_done_stamps_collection_id_and_name(monkeypatch) -> None:
    update = AsyncMock()
    monkeypatch.setattr(facade_module.TransferApi, "update", update)
    facade = TransferTrackerFacade(_postgres_yielding(MagicMock()))

    transfer_id, collection_id = uuid.uuid4(), uuid.uuid4()
    await facade.mark_done(
        transfer_id,
        datetime.now(UTC),
        collection_id=collection_id,
        collection_name="DemoCollection (imported)",
        counts={"documents": 2},
    )

    update.assert_awaited_once()
    kwargs = update.await_args.kwargs
    assert kwargs["status"] == TransferStatus.DONE
    assert kwargs["progress"] == 100
    assert kwargs["collection_id"] == collection_id
    assert kwargs["collection_name"] == "DemoCollection (imported)"


async def test_reap_stale_marks_each_stale_running_transfer_failed(monkeypatch) -> None:
    stale = [SimpleNamespace(id=uuid.uuid4()), SimpleNamespace(id=uuid.uuid4())]
    monkeypatch.setattr(facade_module.TransferApi, "list_stale", AsyncMock(return_value=stale))
    update = AsyncMock()
    monkeypatch.setattr(facade_module.TransferApi, "update", update)
    facade = TransferTrackerFacade(_postgres_yielding(MagicMock()))

    reaped = await facade.reap_stale(10800)

    # Every stale RUNNING transfer the query returned is driven to FAILED (terminal + GC-reclaimable).
    assert reaped == [stale[0].id, stale[1].id]
    assert update.await_count == 2
    for call, row in zip(update.await_args_list, stale, strict=True):
        assert call.args[1] == row.id
        assert call.kwargs["status"] == TransferStatus.FAILED
        assert "reaped" in call.kwargs["error"]
        assert call.kwargs["finished_at"] is not None


async def test_reap_stale_is_a_noop_when_nothing_is_stale(monkeypatch) -> None:
    # A fresh/recent RUNNING transfer never appears in list_stale (its updated_at is within the
    # horizon), so the reaper writes NOTHING — no false-failing a healthy in-flight transfer.
    monkeypatch.setattr(facade_module.TransferApi, "list_stale", AsyncMock(return_value=[]))
    update = AsyncMock()
    monkeypatch.setattr(facade_module.TransferApi, "update", update)
    facade = TransferTrackerFacade(_postgres_yielding(MagicMock()))

    reaped = await facade.reap_stale(10800)

    assert reaped == []
    update.assert_not_awaited()


async def test_list_stale_query_filters_running_and_frozen_updated_at() -> None:
    """The staleness discrimination is the WHERE: only RUNNING rows whose updated_at froze past the
    horizon match — a fresh/recent RUNNING row (updated_at within the horizon) is excluded."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)

    await TransferApi.list_stale(session, 10800)

    statement = session.execute.await_args.args[0]
    # Plain rendering (not literal_binds): the interval bind is a timedelta that has no SQL literal,
    # so assert on the columns the WHERE gates (bind VALUES are parameterised, not inlined).
    sql = str(statement).lower()
    where = sql.split("where", 1)[1]
    assert "status" in where  # only RUNNING transfers are candidates (status = RUNNING bind)
    assert "updated_at" in where  # gated on the frozen-progress horizon, so fresh rows are excluded
