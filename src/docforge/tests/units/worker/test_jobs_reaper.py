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

    await JobApi.list_stale(
        _CapturingSession(), older_than_seconds=1200, heartbeat_stale_seconds=180
    )

    sql = str(
        captured["statement"].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    ).lower()
    # RUNNING-only: a PENDING/queued row is never a reap candidate.
    assert "status" in sql and "running" in sql
    # DB clock, not Python: the cutoff is now() minus an interval, so a worker/DB skew can't misjudge.
    assert "now()" in sql and "make_interval" in sql


async def test_list_stale_joins_heartbeats_so_a_live_worker_vetoes_the_reap() -> None:
    """
    The reap candidate set is gated by the worker's heartbeat: the query LEFT-joins
    ``worker_heartbeats`` on ``job.worker_id`` and only keeps a job whose heartbeat is ABSENT or
    STALE. A fresh heartbeat therefore fails the WHERE and is vetoed — a healthy job running one long
    silent stage on a live worker is never reaped (Finding 1). Proven on the compiled SQL because the
    unit suite has no real Postgres to exercise the join behaviourally (that lives in the live suite).
    """
    captured: dict[str, object] = {}

    class _CapturingSession:
        async def execute(self, statement):
            captured["statement"] = statement
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            return result

    from shared_libs.services.db.postgresql.apis import JobApi  # noqa: PLC0415

    await JobApi.list_stale(
        _CapturingSession(), older_than_seconds=1200, heartbeat_stale_seconds=180
    )

    sql = str(
        captured["statement"].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    ).lower()
    # The heartbeat table is joined (LEFT OUTER, so an absent heartbeat still surfaces the job).
    assert "worker_heartbeats" in sql and "left outer join" in sql
    # The veto predicate: reap only when the heartbeat is ABSENT (worker_id IS NULL) OR STALE
    # (last_seen older than its own now() - interval cutoff). A fresh last_seen fails both → vetoed.
    assert "worker_heartbeats.worker_id is null" in sql
    assert "worker_heartbeats.last_seen" in sql
    # TWO independent DB-clock cutoffs now: the silence cutoff on the job + the heartbeat cutoff.
    assert sql.count("make_interval") == 2


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
    # _terminate now edge-guards the document write on job ownership: THIS job is the document's latest
    # here (no newer reingest), so the mirror proceeds for every stale job.
    get_latest = AsyncMock(
        side_effect=lambda session, document_id: SimpleNamespace(
            id=next(job.id for job in stale if job.document_id == document_id)
        )
    )
    monkeypatch.setattr(facade_module.JobApi, "mark_terminal", mark_terminal)
    monkeypatch.setattr(facade_module.JobApi, "get_latest_for_document", get_latest)
    monkeypatch.setattr(facade_module.DocumentApi, "set_status", set_status)

    facade = JobsFacade(_postgres_yielding(MagicMock()))
    reaped = await facade.reap_stale(older_than_seconds=1200, heartbeat_stale_seconds=180)

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
    reaped = await facade.reap_stale(older_than_seconds=1200, heartbeat_stale_seconds=180)

    assert reaped == []
    mark_terminal.assert_not_awaited()
    set_status.assert_not_awaited()


async def test_terminate_does_not_clobber_a_newer_jobs_document_state(monkeypatch) -> None:
    """
    Ownership edge-guard (Finding 2): reaping an OLD wedged job must NOT overwrite the document's
    terminal state written by a NEWER job (a reingest queued while the old one hung). The old job row
    is still marked terminal, but the shared DOCUMENT write is SKIPPED because a newer job owns it.
    """
    old_job = SimpleNamespace(id=uuid.uuid4(), document_id=uuid.uuid4())
    newer_job_id = uuid.uuid4()  # the document's current owner — a different, newer job
    monkeypatch.setattr(facade_module.JobApi, "list_stale", AsyncMock(return_value=[old_job]))
    mark_terminal = AsyncMock(
        return_value=SimpleNamespace(id=old_job.id, document_id=old_job.document_id)
    )
    # get_latest_for_document returns the NEWER job, so the old reaped job is not the owner.
    get_latest = AsyncMock(return_value=SimpleNamespace(id=newer_job_id))
    set_status = AsyncMock()
    monkeypatch.setattr(facade_module.JobApi, "mark_terminal", mark_terminal)
    monkeypatch.setattr(facade_module.JobApi, "get_latest_for_document", get_latest)
    monkeypatch.setattr(facade_module.DocumentApi, "set_status", set_status)

    facade = JobsFacade(_postgres_yielding(MagicMock()))
    reaped = await facade.reap_stale(older_than_seconds=1200, heartbeat_stale_seconds=180)

    # The job row is still terminated (it genuinely is over)...
    assert reaped == [old_job.id]
    mark_terminal.assert_awaited_once()
    # ...but the document write is vetoed: the newer job owns the document's state now.
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

    # The reap now carries BOTH cutoffs: the silence threshold AND the heartbeat-veto cutoff (a fresh
    # heartbeat vetoes the reap), so it is called with (WORKER_REAP_STALE_SECONDS, WORKER_PRUNE_STALE_SECONDS).
    reap_stale.assert_awaited_once_with(1200, 180)
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


# --------------------------------------------------------------------------- #
# JobApi.mark_running — the claim transition (zombie-retry hardening, Finding 2)
# --------------------------------------------------------------------------- #


class _GetSession:
    """A session whose ``get`` returns a preset row — enough for mark_running's single fetch."""

    def __init__(self, job) -> None:
        self._job = job

    async def get(self, _model, _pk):
        return self._job


async def test_mark_running_clears_the_cancel_flag_on_a_fresh_attempt() -> None:
    """
    A fresh claim starts UNFLAGGED: the reaper/force-terminate raise ``cancel_requested`` as a
    backstop stop signal, so a legitimately re-run job must have it cleared — otherwise the
    CancellationGuard would fire on a stale flag and spuriously cancel the new attempt (Finding 2).
    """
    from shared_libs.services.db.postgresql.apis import JobApi  # noqa: PLC0415

    job = SimpleNamespace(
        status=JobStatus.PENDING,
        worker_id=None,
        attempt=0,
        started_at=None,
        error="old error",
        finished_at=object(),
        current_stage="stale",
        progress=42,
        cancel_requested=True,  # a stale backstop flag from a previous terminated attempt
    )
    import datetime as _dt  # noqa: PLC0415

    await JobApi.mark_running(
        _GetSession(job), uuid.uuid4(), "w1", attempt=1, started_at=_dt.datetime.now(_dt.UTC)
    )

    assert job.status == JobStatus.RUNNING
    assert job.cancel_requested is False  # the stale flag is cleared
    assert job.error is None and job.finished_at is None and job.progress == 0


async def test_mark_running_refuses_to_resurrect_a_terminal_job() -> None:
    """
    Defense-in-depth: a zombie arq re-delivery of a job the reaper already marked FAILED (or a
    force-terminated CANCELLED / a completed DONE) must NOT be flipped back to RUNNING. mark_running
    is a no-op on any terminal status, so no path can un-finish a finished job (Finding 2).
    """
    import datetime as _dt  # noqa: PLC0415

    from shared_libs.services.db.postgresql.apis import JobApi  # noqa: PLC0415

    for terminal in (JobStatus.FAILED, JobStatus.DONE, JobStatus.CANCELLED):
        job = SimpleNamespace(
            status=terminal,
            worker_id="dead-worker",
            attempt=3,
            started_at=object(),
            error="reaped: ...",
            finished_at=object(),
            current_stage=None,
            progress=100,
            cancel_requested=True,
        )
        await JobApi.mark_running(
            _GetSession(job), uuid.uuid4(), "w2", attempt=4, started_at=_dt.datetime.now(_dt.UTC)
        )
        # Untouched: status stays terminal, the backstop cancel flag is not cleared, worker not stolen.
        assert job.status == terminal
        assert job.worker_id == "dead-worker"
        assert job.cancel_requested is True


# --------------------------------------------------------------------------- #
# reclaim_worker_jobs — startup hygiene, SAME-HOSTNAME restart ONLY
# --------------------------------------------------------------------------- #
#
# ``worker_id`` is the container hostname (``socket.gethostname()``), which is stable ONLY within a
# container's lifetime. Reclaim therefore recovers a same-container restart's own orphans (a dev
# hot-reload / in-place respawn keeps the hostname) but is a deliberate NO-OP after a crash/recreate
# that mints a fresh hostname — those orphans carry the OLD id, and the heartbeat reaper (reap_stale)
# is what recovers them. These tests lock that real, narrowed contract.


async def test_list_running_for_worker_matches_only_that_exact_worker_id() -> None:
    """The reclaim predicate is scoped to EXACTLY the caller's id (RUNNING + worker_id = :id).

    Proving the ``worker_id = :id`` equality on the compiled SQL is what guarantees the two contract
    properties: a starting replica never touches a SIBLING's live rows, AND a post-recreate worker
    (new hostname) matches NONE of the old incarnation's orphans — leaving those to the reaper.
    """
    captured: dict[str, object] = {}

    class _CapturingSession:
        async def execute(self, statement):
            captured["statement"] = statement
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            return result

    from shared_libs.services.db.postgresql.apis import JobApi  # noqa: PLC0415

    await JobApi.list_running_for_worker(_CapturingSession(), "docforge-worker-abc123")

    sql = str(
        captured["statement"].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    ).lower()
    # RUNNING-only, and keyed on an EXACT worker_id equality (never a broad/shared match).
    assert "status" in sql and "running" in sql
    assert "job.worker_id = 'docforge-worker-abc123'" in sql


async def test_reclaim_fails_each_own_orphan_and_its_document(monkeypatch) -> None:
    """A same-hostname restart: every RUNNING row still stamped with THIS id is failed + its doc."""
    orphans = [
        SimpleNamespace(id=uuid.uuid4(), document_id=uuid.uuid4()),
        SimpleNamespace(id=uuid.uuid4(), document_id=uuid.uuid4()),
    ]
    doc_by_job = {job.id: job.document_id for job in orphans}
    monkeypatch.setattr(
        facade_module.JobApi, "list_running_for_worker", AsyncMock(return_value=orphans)
    )
    mark_terminal = AsyncMock(
        side_effect=lambda session, job_id, **kw: SimpleNamespace(
            id=job_id, document_id=doc_by_job[job_id]
        )
    )
    get_latest = AsyncMock(
        side_effect=lambda session, document_id: SimpleNamespace(
            id=next(job.id for job in orphans if job.document_id == document_id)
        )
    )
    set_status = AsyncMock()
    monkeypatch.setattr(facade_module.JobApi, "mark_terminal", mark_terminal)
    monkeypatch.setattr(facade_module.JobApi, "get_latest_for_document", get_latest)
    monkeypatch.setattr(facade_module.DocumentApi, "set_status", set_status)

    facade = JobsFacade(_postgres_yielding(MagicMock()))
    reclaimed = await facade.reclaim_worker_jobs("docforge-worker-abc123")

    # Every own orphan is returned, marked terminal FAILED, and its document flagged FAILED.
    assert reclaimed == [orphans[0].id, orphans[1].id]
    assert mark_terminal.await_count == 2
    for call in mark_terminal.await_args_list:
        assert call.kwargs["status"] == JobStatus.FAILED
    # The reason reads like startup reclaim (a same-container restart), never a "cancelled:" prefix.
    reason = mark_terminal.await_args_list[0].kwargs["reason"]
    assert reason.startswith("reclaimed at worker startup")
    assert not reason.lower().startswith("cancelled")
    assert set_status.await_count == 2
    for call in set_status.await_args_list:
        assert call.args[2] == DocumentStatus.FAILED


async def test_reclaim_is_a_noop_after_a_container_recreate(monkeypatch) -> None:
    """A crash/recreate mints a NEW hostname, so the OLD incarnation's orphans (stamped with the old
    id) match nothing under the new id — reclaim is a clean no-op. This is CORRECT, not a miss: the
    heartbeat reaper recovers cross-recreate orphans once the dead worker's heartbeat ages out."""
    # The new incarnation's id finds no rows (its predicate is worker_id = <new id>; the orphans
    # carry <old id>), exactly what the real query returns after a recreate.
    monkeypatch.setattr(facade_module.JobApi, "list_running_for_worker", AsyncMock(return_value=[]))
    mark_terminal = AsyncMock()
    set_status = AsyncMock()
    monkeypatch.setattr(facade_module.JobApi, "mark_terminal", mark_terminal)
    monkeypatch.setattr(facade_module.DocumentApi, "set_status", set_status)

    facade = JobsFacade(_postgres_yielding(MagicMock()))
    reclaimed = await facade.reclaim_worker_jobs("docforge-worker-NEW-hostname")

    assert reclaimed == []
    mark_terminal.assert_not_awaited()
    set_status.assert_not_awaited()
