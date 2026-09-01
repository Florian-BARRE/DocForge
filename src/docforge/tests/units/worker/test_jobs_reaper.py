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
from shared_libs.services.db.postgresql.tables import DocumentStatus, JobStatus


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
    doc_by_job = {job.id: job.document_id for job in stale}
    monkeypatch.setattr(facade_module.JobApi, "list_stale", AsyncMock(return_value=stale))
    # reap_stale now routes through the SHARED force-terminate path: JobApi.mark_terminal (which
    # returns the terminated job so the facade can mirror its document) + DocumentApi.set_status.
    mark_terminal = AsyncMock(
        side_effect=lambda session, job_id, **kw: SimpleNamespace(
            id=job_id, document_id=doc_by_job[job_id]
        )
    )
    set_status = AsyncMock()
    monkeypatch.setattr(facade_module.JobApi, "mark_terminal", mark_terminal)
    monkeypatch.setattr(facade_module.DocumentApi, "set_status", set_status)

    facade = JobsFacade(_postgres_yielding(MagicMock()))
    reaped = await facade.reap_stale(older_than_seconds=1200)

    # Every stale job is returned, marked terminal FAILED, and its owning document flagged FAILED.
    assert reaped == [stale[0].id, stale[1].id]
    assert mark_terminal.await_count == 2
    assert {call.args[1] for call in mark_terminal.await_args_list} == {stale[0].id, stale[1].id}
    for call in mark_terminal.await_args_list:
        assert call.kwargs["status"] == JobStatus.FAILED
    # The operator-clear reason names the minutes and the presumed cause, and — because the reaper's
    # terminal status is FAILED — it must read like a REAP, never a "cancelled:" (that prefix belongs
    # to the CANCELLED cancel path; a failed chip carrying "cancelled:" is the contradiction QA caught).
    reason = mark_terminal.await_args_list[0].kwargs["reason"]
    assert "20m" in reason and "orphaned" in reason
    assert reason.startswith("reaped:")
    assert not reason.lower().startswith("cancelled")
    assert set_status.await_count == 2
    for call in set_status.await_args_list:
        assert call.args[2] == DocumentStatus.FAILED
    assert {call.args[1] for call in set_status.await_args_list} == {
        stale[0].document_id,
        stale[1].document_id,
    }


async def test_reap_stale_is_a_noop_when_nothing_is_stale(monkeypatch) -> None:
    monkeypatch.setattr(facade_module.JobApi, "list_stale", AsyncMock(return_value=[]))
    mark_terminal = AsyncMock()
    set_status = AsyncMock()
    monkeypatch.setattr(facade_module.JobApi, "mark_terminal", mark_terminal)
    monkeypatch.setattr(facade_module.DocumentApi, "set_status", set_status)

    facade = JobsFacade(_postgres_yielding(MagicMock()))
    reaped = await facade.reap_stale(older_than_seconds=1200)

    assert reaped == []
    mark_terminal.assert_not_awaited()
    set_status.assert_not_awaited()


# --------------------------------------------------------------------------- #
# reap_stuck_jobs — the cron coroutine
# --------------------------------------------------------------------------- #


def _reaper_module(worker_jobs_modules):
    """The jobs.reaper module (imported as a side effect of the worker_jobs_modules fixture)."""
    _ = worker_jobs_modules  # forces the one-time fake-backend import of the jobs package
    return sys.modules["jobs.reaper"]


def _fake_context(
    *, enabled: bool, reap_stale: AsyncMock, prune: AsyncMock | None = None
) -> SimpleNamespace:
    return SimpleNamespace(
        RUNTIME_CONFIG=SimpleNamespace(
            WORKER_REAP_ENABLED=enabled,
            WORKER_REAP_STALE_SECONDS=1200,
            WORKER_PRUNE_STALE_SECONDS=180,
        ),
        database=SimpleNamespace(
            jobs=SimpleNamespace(
                reap_stale=reap_stale,
                prune_stale_heartbeats=prune or AsyncMock(return_value=[]),
            )
        ),
        logger=MagicMock(),
    )


async def test_reap_stuck_jobs_reaps_and_returns_ids_when_enabled(
    worker_jobs_modules, monkeypatch
) -> None:
    reaper = _reaper_module(worker_jobs_modules)
    reaped_ids = [uuid.uuid4(), uuid.uuid4()]
    reap_stale = AsyncMock(return_value=reaped_ids)
    prune = AsyncMock(return_value=["worker-dead-1"])
    monkeypatch.setattr(
        reaper, "CONTEXT", _fake_context(enabled=True, reap_stale=reap_stale, prune=prune)
    )

    result = await reaper.reap_stuck_jobs({})

    reap_stale.assert_awaited_once_with(1200)
    # The reaper cron now ALSO prunes crashed workers' stale heartbeats (moved off GET /workers/live).
    prune.assert_awaited_once_with(180)
    assert result == [str(job_id) for job_id in reaped_ids]


async def test_reap_stuck_jobs_is_a_noop_when_disabled(worker_jobs_modules, monkeypatch) -> None:
    reaper = _reaper_module(worker_jobs_modules)
    reap_stale = AsyncMock(return_value=[uuid.uuid4()])
    prune = AsyncMock(return_value=[uuid.uuid4()])
    monkeypatch.setattr(
        reaper, "CONTEXT", _fake_context(enabled=False, reap_stale=reap_stale, prune=prune)
    )

    result = await reaper.reap_stuck_jobs({})

    assert result == []
    reap_stale.assert_not_awaited()
    # Disabled reaper prunes nothing either (the cron isn't registered; a direct call is a full no-op).
    prune.assert_not_awaited()
