"""JobsFacade side-job handling — the ``_terminate`` KIND GATE across every entry point, plus the
``create_metadata_sync`` / ``abandon`` / ``abandon_ingest`` helpers.

Serviceless (JobApi / DocumentApi patched, same stub style as test_jobs_reaper.py). The invariant: a
terminating job's ROW is always terminated, but the owning DOCUMENT status is mirrored ONLY for
``kind == INGEST`` — a ``metadata_sync`` side-job (the document's latest job) must never clobber a
healthy DONE document. Real-SQL proof of the same gate lives in tests/db/.
"""

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared_libs.services.db.facades import JobsFacade
from shared_libs.services.db.facades import jobs_facade as facade_module
from shared_libs.services.db.postgresql.tables import DocumentStatus, JobKind, JobStatus


def _postgres_yielding(session: MagicMock) -> MagicMock:
    @asynccontextmanager
    async def _session():
        yield session

    postgres = MagicMock()
    postgres.session = _session
    return postgres


def _wire(monkeypatch, kind: JobKind, *, latest_is_self: bool = True):
    """Patch the JobApi/DocumentApi seams for ONE job of ``kind``; return (job, mark_terminal, set_status)."""
    job = SimpleNamespace(
        id=uuid.uuid4(), document_id=uuid.uuid4(), current_stage="parse", kind=kind
    )
    mark_terminal = AsyncMock(return_value=job)
    latest = SimpleNamespace(id=job.id if latest_is_self else uuid.uuid4())
    set_status = AsyncMock()
    monkeypatch.setattr(facade_module.JobApi, "mark_terminal", mark_terminal)
    monkeypatch.setattr(
        facade_module.JobApi, "get_latest_for_document", AsyncMock(return_value=latest)
    )
    monkeypatch.setattr(facade_module.DocumentApi, "set_status", set_status)
    monkeypatch.setattr(facade_module.JobApi, "list_stale", AsyncMock(return_value=[job]))
    monkeypatch.setattr(
        facade_module.JobApi, "list_over_job_timeout", AsyncMock(return_value=[(job, 900.0)])
    )
    monkeypatch.setattr(
        facade_module.JobApi, "list_running_for_worker", AsyncMock(return_value=[job])
    )
    return job, mark_terminal, set_status


async def _run_entry_point(facade: JobsFacade, name: str, job) -> object:
    """Drive one of the five termination entry points for ``job``."""
    if name == "force_terminate":
        return await facade.force_terminate(job.id, "manual")
    if name == "reap_stale":
        return await facade.reap_stale(1200, 180)
    if name == "reap_over_job_timeout":
        return await facade.reap_over_job_timeout(1800.0, 300.0, 180)
    if name == "reclaim_worker_jobs":
        return await facade.reclaim_worker_jobs("w-1")
    return await facade.abandon_ingest(job.id, "enqueue failed")


ENTRY_POINTS = [
    "force_terminate",
    "reap_stale",
    "reap_over_job_timeout",
    "reclaim_worker_jobs",
    "abandon_ingest",
]


@pytest.mark.parametrize("entry_point", ENTRY_POINTS)
async def test_metadata_sync_termination_never_writes_document_status(
    monkeypatch, entry_point
) -> None:
    job, mark_terminal, set_status = _wire(monkeypatch, JobKind.METADATA_SYNC)
    facade = JobsFacade(_postgres_yielding(MagicMock()))

    await _run_entry_point(facade, entry_point, job)

    # The job ROW is still terminated (frees the active lock) ...
    mark_terminal.assert_awaited_once()
    # ... but the healthy document is never touched, even though the side-job is its latest job.
    set_status.assert_not_awaited()


@pytest.mark.parametrize("entry_point", ENTRY_POINTS)
async def test_ingest_termination_still_mirrors_document_status(monkeypatch, entry_point) -> None:
    job, mark_terminal, set_status = _wire(monkeypatch, JobKind.INGEST)
    facade = JobsFacade(_postgres_yielding(MagicMock()))

    await _run_entry_point(facade, entry_point, job)

    mark_terminal.assert_awaited_once()
    set_status.assert_awaited_once()
    expected = (
        DocumentStatus.CANCELLED if entry_point == "force_terminate" else DocumentStatus.FAILED
    )
    assert set_status.await_args.args[1] == job.document_id
    assert set_status.await_args.args[2] == expected


async def test_reap_of_metadata_sync_still_reports_the_job_id(monkeypatch) -> None:
    """The kind gate only skips the document write: the reaped id is still returned to the cron."""
    job, _, _ = _wire(monkeypatch, JobKind.METADATA_SYNC)
    facade = JobsFacade(_postgres_yielding(MagicMock()))

    assert await facade.reap_stale(1200, 180) == [job.id]
    assert await facade.reap_over_job_timeout(1800.0, 300.0, 180) == [job.id]
    assert await facade.reclaim_worker_jobs("w-1") == [job.id]


async def test_terminate_skips_document_when_the_job_was_already_terminal(monkeypatch) -> None:
    """mark_terminal -> None (lost the race): nothing is mirrored, whatever the kind."""
    job, mark_terminal, set_status = _wire(monkeypatch, JobKind.INGEST)
    mark_terminal.return_value = None
    facade = JobsFacade(_postgres_yielding(MagicMock()))

    assert await facade.force_terminate(job.id, "manual") is None
    set_status.assert_not_awaited()


async def test_terminate_ingest_job_without_a_document_skips_the_mirror(monkeypatch) -> None:
    job, mark_terminal, set_status = _wire(monkeypatch, JobKind.INGEST)
    mark_terminal.return_value = SimpleNamespace(id=job.id, document_id=None, kind=JobKind.INGEST)
    facade = JobsFacade(_postgres_yielding(MagicMock()))

    await facade.force_terminate(job.id, "manual")

    set_status.assert_not_awaited()


# -------------------- create_metadata_sync / abandon / abandon_ingest --------------------
async def test_create_metadata_sync_inserts_a_pending_metadata_sync_row(monkeypatch) -> None:
    minted_id = uuid.uuid4()

    async def _flush(session, job):
        job.id = minted_id  # what the real INSERT/flush populates

    create = AsyncMock(side_effect=_flush)
    monkeypatch.setattr(facade_module.JobApi, "create", create)
    facade = JobsFacade(_postgres_yielding(MagicMock()))
    document_id, collection_id = uuid.uuid4(), uuid.uuid4()

    returned = await facade.create_metadata_sync(document_id, collection_id)

    create.assert_awaited_once()
    row = create.await_args.args[1]
    assert row.kind == JobKind.METADATA_SYNC
    assert row.status == JobStatus.PENDING
    assert row.document_id == document_id
    assert row.collection_id == collection_id
    # Ingest-only columns stay unset for a side-job.
    assert row.current_stage is None
    assert returned == minted_id


async def test_create_metadata_sync_propagates_the_active_job_conflict(monkeypatch) -> None:
    """The unique-violation is NOT swallowed here: the router owns the best-effort handling."""
    monkeypatch.setattr(
        facade_module.JobApi, "create", AsyncMock(side_effect=RuntimeError("uq_job_active"))
    )
    facade = JobsFacade(_postgres_yielding(MagicMock()))

    with pytest.raises(RuntimeError, match="uq_job_active"):
        await facade.create_metadata_sync(uuid.uuid4(), uuid.uuid4())


async def test_abandon_fails_the_row_without_touching_the_document(monkeypatch) -> None:
    mark_terminal = AsyncMock()
    set_status = AsyncMock()
    monkeypatch.setattr(facade_module.JobApi, "mark_terminal", mark_terminal)
    monkeypatch.setattr(facade_module.DocumentApi, "set_status", set_status)
    facade = JobsFacade(_postgres_yielding(MagicMock()))
    job_id = uuid.uuid4()

    await facade.abandon(job_id, "enqueue failed")

    mark_terminal.assert_awaited_once()
    assert mark_terminal.await_args.args[1] == job_id
    assert mark_terminal.await_args.kwargs["status"] == JobStatus.FAILED
    assert mark_terminal.await_args.kwargs["reason"] == "enqueue failed"
    set_status.assert_not_awaited()


async def test_abandon_swallows_a_db_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        facade_module.JobApi, "mark_terminal", AsyncMock(side_effect=RuntimeError("db down"))
    )
    facade = JobsFacade(_postgres_yielding(MagicMock()))

    await facade.abandon(uuid.uuid4(), "enqueue failed")  # must not raise


async def test_abandon_ingest_swallows_a_db_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        facade_module.JobApi, "mark_terminal", AsyncMock(side_effect=RuntimeError("db down"))
    )
    facade = JobsFacade(_postgres_yielding(MagicMock()))

    await facade.abandon_ingest(uuid.uuid4(), "enqueue failed")  # must not raise
