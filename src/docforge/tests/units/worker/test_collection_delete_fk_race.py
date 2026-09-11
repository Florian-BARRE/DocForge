"""Collection delete vs an in-flight ingest — the FK-race fix (no IntegrityError, graceful stop).

A ``DELETE /collections/{id}`` cascade removes the collection's ``job`` rows (and documents) while a
worker may still be mid-run, inserting ``job_stage_event`` rows (and, at persist, document/chunk rows)
that FK-reference the about-to-vanish rows — which would raise an IntegrityError in the worker. Three
surfaces close the race:

  * ``CollectionsFacade.delete`` cancels the collection's live jobs FIRST (a conditional
    ``mark_terminal`` transition), committed before the cascade, so a live worker aborts at its next
    stage boundary — before it writes anything the cascade deletes.
  * ``JobApi.is_cancel_requested`` treats a VANISHED job row as a stop signal, so the worker still
    stops even if the cascade already removed the job before a stage boundary was reached.
  * ``JobProgressRecorder`` tolerates a vanished-job FK on its stage-event insert (swallows it rather
    than crashing the progress callback) for the residual between-boundaries insert window.

Postgres is fully mocked (the session-yielding stub shared with test_jobs_reaper / test_jobs_progress).
"""

import sys
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from shared_libs.pipelines.engine import ProgressEvent, ProgressPhase
from shared_libs.services.db.facades import collections_facade as cf_module
from shared_libs.services.db.facades.collections_facade import CollectionsFacade
from shared_libs.services.db.postgresql.apis import JobApi
from shared_libs.services.db.postgresql.tables import JobStatus


def _postgres_yielding(session: MagicMock) -> MagicMock:
    """A postgres mock whose session() is an async context manager yielding ``session``."""

    @asynccontextmanager
    async def _session():
        yield session

    postgres = MagicMock()
    postgres.session = _session
    return postgres


# --------------------------------------------------------------------------- #
# CollectionsFacade.delete — cancels in-flight jobs BEFORE the cascade
# --------------------------------------------------------------------------- #


async def test_delete_cancels_active_jobs_before_the_cascade_without_raising(monkeypatch) -> None:
    """A delete with a live job marks it terminal FIRST, then cascades — and never raises."""
    collection_id = uuid.uuid4()
    active_job = SimpleNamespace(id=uuid.uuid4(), document_id=uuid.uuid4())
    order: list[str] = []

    session = MagicMock()
    session.flush = AsyncMock()
    facade = CollectionsFacade(_postgres_yielding(session), MagicMock(), MagicMock())

    # The in-flight job + the conditional terminal transition (records the ordering vs the cascade).
    async def _list_active(_session, _collection_id):
        return [active_job]

    async def _mark_terminal(_session, job_id, *, status, reason, finished_at, error_type=None):
        order.append("cancel")
        assert status is JobStatus.CANCELLED
        assert job_id == active_job.id
        return active_job

    async def _delete(_session, _collection_id):
        order.append("cascade")

    monkeypatch.setattr(JobApi, "list_active_for_collection", _list_active)
    monkeypatch.setattr(JobApi, "mark_terminal", _mark_terminal)
    monkeypatch.setattr(JobApi, "list_job_ids_for_collection", AsyncMock(return_value=[]))
    monkeypatch.setattr(cf_module.QdrantCollectionApi, "drop", AsyncMock())
    monkeypatch.setattr(
        cf_module.CollectionApi, "get", AsyncMock(return_value=SimpleNamespace(id=collection_id))
    )
    monkeypatch.setattr(cf_module.CollectionApi, "delete", _delete)
    monkeypatch.setattr(
        cf_module.BlobApi, "collect_hashes_for_collection", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(cf_module.BlobApi, "delete_unreferenced", AsyncMock(return_value=[]))
    monkeypatch.setattr(cf_module.TracePurgeHelper, "purge", AsyncMock())

    existed = await facade.delete(collection_id)

    assert existed is True
    # Cancel-first is the whole point: the live job is terminated BEFORE the cascade deletes its row.
    assert order == ["cancel", "cascade"]


# --------------------------------------------------------------------------- #
# JobApi.is_cancel_requested — a vanished job row is a STOP signal
# --------------------------------------------------------------------------- #


class _RowResult:
    """An execute() result whose .first() yields the given row (None = the job row is gone)."""

    def __init__(self, row: object | None) -> None:
        self._row = row

    def first(self) -> object | None:
        return self._row


def _session_returning(row: object | None) -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock(return_value=_RowResult(row))
    return session


async def test_is_cancel_requested_true_when_the_job_row_vanished() -> None:
    """A deleted job (cascade) reads as cancel-requested, so the worker stops at its next boundary."""
    assert await JobApi.is_cancel_requested(_session_returning(None), uuid.uuid4()) is True


async def test_is_cancel_requested_reflects_the_flag_while_the_job_still_exists() -> None:
    """A present job returns its actual flag — unchanged behaviour for the normal cancel path."""
    present_unflagged = SimpleNamespace(id=uuid.uuid4(), cancel_requested=False)
    present_flagged = SimpleNamespace(id=uuid.uuid4(), cancel_requested=True)
    assert (
        await JobApi.is_cancel_requested(_session_returning(present_unflagged), uuid.uuid4())
        is False
    )
    assert (
        await JobApi.is_cancel_requested(_session_returning(present_flagged), uuid.uuid4()) is True
    )


# --------------------------------------------------------------------------- #
# JobProgressRecorder — a vanished-job FK on the stage-event insert is tolerated
# --------------------------------------------------------------------------- #


@pytest.fixture
def progress_module(worker_jobs_modules):
    """The jobs.progress module (imported under the fake backend by the session fixture)."""
    return sys.modules["jobs.progress"]


async def test_progress_recorder_tolerates_a_vanished_job_on_stage_open(
    progress_module, monkeypatch
) -> None:
    """A stage START whose event insert FK-fails (job deleted mid-run) does not crash the callback."""
    jobs = MagicMock()
    # The cascade removed the job row → the stage-event insert FK-fails.
    jobs.record_event = AsyncMock(
        side_effect=IntegrityError("insert", {}, Exception("FK violation"))
    )
    jobs.set_progress = AsyncMock()
    jobs.set_items = AsyncMock()
    context = SimpleNamespace(database=SimpleNamespace(jobs=jobs))
    monkeypatch.setattr(progress_module, "CONTEXT", context)

    recorder = progress_module.JobProgressRecorder(uuid.uuid4(), ["parser"])

    # Must NOT raise; the open-event bookkeeping stays empty and the run still advances its progress.
    await recorder(
        ProgressEvent(phase=ProgressPhase.START, node_id="parser", kind="parser", record=None)
    )
    assert recorder._open_event_id is None
    assert recorder._open_stage is None
    jobs.set_progress.assert_awaited()
