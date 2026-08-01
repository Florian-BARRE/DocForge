"""Stuck-job reaper — the recovery path for jobs orphaned by a worker hot-reload/crash.

Three surfaces:
  * JobApi.list_stale — the PREDICATE: RUNNING-only, DB-clock cutoff (so PENDING/DONE/FAILED and
    recently-updated RUNNING rows are never candidates). Proven by compiling the real statement.
  * JobsFacade.reap_stale — the ORCHESTRATION: each stale job marked FAILED + its document FAILED,
    the reaped ids returned; nothing stale => a clean no-op.
  * reap_stuck_jobs — the CRON coroutine: honours WORKER_REAP_ENABLED and forwards the threshold.

Postgres is fully mocked (same session-yielding stub as test_ingestion_facade.py).
"""

import sys
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.dialects import postgresql

from shared_libs.services.db.facades import JobsFacade
from shared_libs.services.db.facades import jobs_facade as facade_module
from shared_libs.services.db.postgresql.tables import DocumentStatus


def _postgres_yielding(session: MagicMock) -> MagicMock:
    """A postgres mock whose session() is an async context manager yielding ``session``."""

    @asynccontextmanager
    async def _session():
        yield session

    postgres = MagicMock()
    postgres.session = _session
    return postgres


# --------------------------------------------------------------------------- #
# JobApi.list_stale — the predicate
# --------------------------------------------------------------------------- #


async def test_list_stale_filters_running_and_uses_the_db_clock() -> None:
    """The query touches ONLY running rows and cuts on now() - interval — never Python's clock."""
    captured: dict[str, object] = {}

    class _CapturingSession:
        async def execute(self, statement):
            captured["statement"] = statement
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            return result

    from shared_libs.services.db.postgresql.apis import JobApi  # noqa: PLC0415

    await JobApi.list_stale(_CapturingSession(), older_than_seconds=1200)

    sql = str(
        captured["statement"].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    ).lower()
    # RUNNING-only: a PENDING/queued row is never a reap candidate.
    assert "status" in sql and "running" in sql
    # DB clock, not Python: the cutoff is now() minus an interval, so a worker/DB skew can't misjudge.
    assert "now()" in sql and "make_interval" in sql


# --------------------------------------------------------------------------- #
# JobsFacade.reap_stale — the orchestration
# --------------------------------------------------------------------------- #


async def test_reap_stale_fails_each_stale_job_and_its_document(monkeypatch) -> None:
    stale = [
        SimpleNamespace(id=uuid.uuid4(), document_id=uuid.uuid4()),
        SimpleNamespace(id=uuid.uuid4(), document_id=uuid.uuid4()),
    ]
    monkeypatch.setattr(facade_module.JobApi, "list_stale", AsyncMock(return_value=stale))
    mark_failed = AsyncMock()
    set_status = AsyncMock()
    monkeypatch.setattr(facade_module.JobApi, "mark_failed", mark_failed)
    monkeypatch.setattr(facade_module.DocumentApi, "set_status", set_status)

    facade = JobsFacade(_postgres_yielding(MagicMock()))
    reaped = await facade.reap_stale(older_than_seconds=1200)

    # Every stale job is returned, marked FAILED, and its owning document flagged FAILED.
    assert reaped == [stale[0].id, stale[1].id]
    assert mark_failed.await_count == 2
    assert {call.args[1] for call in mark_failed.await_args_list} == {stale[0].id, stale[1].id}
    # The operator-clear reason names the minutes and the presumed cause.
    reason = mark_failed.await_args_list[0].kwargs["error"]
    assert "20m" in reason and "orphaned" in reason
    assert set_status.await_count == 2
    for call in set_status.await_args_list:
        assert call.args[2] == DocumentStatus.FAILED
    assert {call.args[1] for call in set_status.await_args_list} == {
        stale[0].document_id,
        stale[1].document_id,
    }


async def test_reap_stale_is_a_noop_when_nothing_is_stale(monkeypatch) -> None:
    monkeypatch.setattr(facade_module.JobApi, "list_stale", AsyncMock(return_value=[]))
    mark_failed = AsyncMock()
    set_status = AsyncMock()
    monkeypatch.setattr(facade_module.JobApi, "mark_failed", mark_failed)
    monkeypatch.setattr(facade_module.DocumentApi, "set_status", set_status)

    facade = JobsFacade(_postgres_yielding(MagicMock()))
    reaped = await facade.reap_stale(older_than_seconds=1200)

    assert reaped == []
    mark_failed.assert_not_awaited()
    set_status.assert_not_awaited()


# --------------------------------------------------------------------------- #
# reap_stuck_jobs — the cron coroutine
# --------------------------------------------------------------------------- #


def _reaper_module(worker_jobs_modules):
    """The jobs.reaper module (imported as a side effect of the worker_jobs_modules fixture)."""
    _ = worker_jobs_modules  # forces the one-time fake-backend import of the jobs package
    return sys.modules["jobs.reaper"]


def _fake_context(*, enabled: bool, reap_stale: AsyncMock) -> SimpleNamespace:
    return SimpleNamespace(
        RUNTIME_CONFIG=SimpleNamespace(WORKER_REAP_ENABLED=enabled, WORKER_REAP_STALE_SECONDS=1200),
        database=SimpleNamespace(jobs=SimpleNamespace(reap_stale=reap_stale)),
        logger=MagicMock(),
    )


async def test_reap_stuck_jobs_reaps_and_returns_ids_when_enabled(
    worker_jobs_modules, monkeypatch
) -> None:
    reaper = _reaper_module(worker_jobs_modules)
    reaped_ids = [uuid.uuid4(), uuid.uuid4()]
    reap_stale = AsyncMock(return_value=reaped_ids)
    monkeypatch.setattr(reaper, "CONTEXT", _fake_context(enabled=True, reap_stale=reap_stale))

    result = await reaper.reap_stuck_jobs({})

    reap_stale.assert_awaited_once_with(1200)
    assert result == [str(job_id) for job_id in reaped_ids]


async def test_reap_stuck_jobs_is_a_noop_when_disabled(worker_jobs_modules, monkeypatch) -> None:
    reaper = _reaper_module(worker_jobs_modules)
    reap_stale = AsyncMock(return_value=[uuid.uuid4()])
    monkeypatch.setattr(reaper, "CONTEXT", _fake_context(enabled=False, reap_stale=reap_stale))

    result = await reaper.reap_stuck_jobs({})

    assert result == []
    reap_stale.assert_not_awaited()
