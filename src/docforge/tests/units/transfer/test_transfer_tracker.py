"""TransferTrackerFacade.mark_done — the terminal-success write for a collection-transfer row.

Pins that a completed IMPORT stamps BOTH the new collection's id AND its name onto the tracking row,
so a polled ``GET /transfers/{id}`` surfaces the real name instead of the null the UI falls back to
generic text for. Postgres is mocked (the same session-yielding stub the other facade tests use).
"""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from shared_libs.services.db.facades import TransferTrackerFacade
from shared_libs.services.db.facades import transfer_tracker_facade as facade_module
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
