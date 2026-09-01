"""Transfer GC cron — reclaim expired export bundles (S3 object + tracking row).

Two surfaces:
  * CollectionTransferFacade.gc_expired_bundles — the ORCHESTRATION: every expired export row has its
    S3 object dropped THEN its row deleted (bytes-first), and the reclaimed ids are returned.
  * gc_expired_transfers — the CRON coroutine: honours WORKER_TRANSFER_GC_ENABLED and forwards now().

Postgres + S3 are mocked (the same session-yielding stub the other facade tests use).
"""

import sys
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from shared_libs.services.db.facades import transfer_facade as facade_module
from shared_libs.services.db.facades.transfer_facade import CollectionTransferFacade


def _postgres_yielding(session: MagicMock) -> MagicMock:
    """A postgres mock whose session() is an async context manager yielding ``session``."""

    @asynccontextmanager
    async def _session():
        yield session

    postgres = MagicMock()
    postgres.session = _session
    return postgres


def _s3_yielding() -> MagicMock:
    """An S3 mock whose client() is an async context manager yielding a dummy client."""

    @asynccontextmanager
    async def _client():
        yield object()

    s3 = MagicMock()
    s3.client = _client
    s3.bucket = "bucket"
    return s3


# --------------------------------------------------------------------------- #
# CollectionTransferFacade.gc_expired_bundles — the orchestration
# --------------------------------------------------------------------------- #


async def test_gc_deletes_s3_object_then_row_for_each_expired(monkeypatch) -> None:
    expired = [
        SimpleNamespace(id=uuid.uuid4(), s3_key="collection-exports/a.dcexport"),
        SimpleNamespace(id=uuid.uuid4(), s3_key="collection-exports/b.dcexport"),
    ]
    list_expired = AsyncMock(return_value=expired)
    delete_row = AsyncMock()
    delete_object = AsyncMock()
    monkeypatch.setattr(facade_module.TransferApi, "list_expired", list_expired)
    monkeypatch.setattr(facade_module.TransferApi, "delete", delete_row)
    monkeypatch.setattr(facade_module.S3ObjectApi, "delete", delete_object)

    facade = CollectionTransferFacade(_postgres_yielding(MagicMock()), MagicMock(), _s3_yielding())
    now = datetime.now(UTC)
    reclaimed = await facade.gc_expired_bundles(now)

    # Every expired export is reclaimed everywhere: its S3 object dropped AND its row deleted.
    assert reclaimed == [expired[0].id, expired[1].id]
    assert delete_object.await_count == 2
    assert {call.args[2] for call in delete_object.await_args_list} == {
        "collection-exports/a.dcexport",
        "collection-exports/b.dcexport",
    }
    assert {call.args[1] for call in delete_row.await_args_list} == {expired[0].id, expired[1].id}


async def test_gc_is_a_noop_when_nothing_expired(monkeypatch) -> None:
    monkeypatch.setattr(facade_module.TransferApi, "list_expired", AsyncMock(return_value=[]))
    delete_row = AsyncMock()
    delete_object = AsyncMock()
    monkeypatch.setattr(facade_module.TransferApi, "delete", delete_row)
    monkeypatch.setattr(facade_module.S3ObjectApi, "delete", delete_object)

    facade = CollectionTransferFacade(_postgres_yielding(MagicMock()), MagicMock(), _s3_yielding())
    reclaimed = await facade.gc_expired_bundles(datetime.now(UTC))

    assert reclaimed == []
    delete_object.assert_not_awaited()
    delete_row.assert_not_awaited()


# --------------------------------------------------------------------------- #
# gc_expired_transfers — the cron coroutine
# --------------------------------------------------------------------------- #


def _gc_module(worker_jobs_modules):
    """The jobs.transfer_gc module (imported as a side effect of the worker_jobs_modules fixture)."""
    _ = worker_jobs_modules  # forces the one-time fake-backend import of the jobs package
    return sys.modules["jobs.transfer_gc"]


def _fake_context(*, enabled: bool, gc: AsyncMock) -> SimpleNamespace:
    return SimpleNamespace(
        RUNTIME_CONFIG=SimpleNamespace(WORKER_TRANSFER_GC_ENABLED=enabled),
        database=SimpleNamespace(transfer=SimpleNamespace(gc_expired_bundles=gc)),
        logger=MagicMock(),
    )


async def test_gc_cron_reclaims_and_returns_ids_when_enabled(
    worker_jobs_modules, monkeypatch
) -> None:
    module = _gc_module(worker_jobs_modules)
    reclaimed = [uuid.uuid4(), uuid.uuid4()]
    gc = AsyncMock(return_value=reclaimed)
    monkeypatch.setattr(module, "CONTEXT", _fake_context(enabled=True, gc=gc))

    result = await module.gc_expired_transfers({})

    gc.assert_awaited_once()
    assert result == [str(transfer_id) for transfer_id in reclaimed]


async def test_gc_cron_is_a_noop_when_disabled(worker_jobs_modules, monkeypatch) -> None:
    module = _gc_module(worker_jobs_modules)
    gc = AsyncMock(return_value=[uuid.uuid4()])
    monkeypatch.setattr(module, "CONTEXT", _fake_context(enabled=False, gc=gc))

    result = await module.gc_expired_transfers({})

    assert result == []
    gc.assert_not_awaited()
