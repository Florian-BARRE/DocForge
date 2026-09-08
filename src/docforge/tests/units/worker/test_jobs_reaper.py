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
    # RUNNING-only: the exact equality (not a loose "status"/"running" substring, which would
    # also pass on e.g. a "current_stage" column or an unrelated "running" literal elsewhere)
    # — a PENDING/queued row is never a reap candidate.
    assert "job.status = 'running'" in sql
    # DB clock, not Python: the cutoff is job.updated_at compared against now() minus an
    # interval, so a worker/DB skew can't misjudge.
    assert "job.updated_at < now() - make_interval" in sql


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
    # The heartbeat table is joined (LEFT OUTER on job.worker_id, so an absent heartbeat still
    # surfaces the job rather than dropping it via an inner join).
    assert "left outer join worker_heartbeats on worker_heartbeats.worker_id = job.worker_id" in sql
    # The veto predicate: reap only when the heartbeat is ABSENT (worker_id IS NULL) OR STALE
    # (last_seen older than its own now() - interval cutoff). A fresh last_seen fails both → vetoed.
    assert "worker_heartbeats.worker_id is null" in sql
    assert "worker_heartbeats.last_seen < now() - make_interval" in sql
    # TWO independent DB-clock cutoffs now: the silence cutoff on the job + the heartbeat cutoff.
    assert sql.count("make_interval") == 2


async def test_list_over_job_timeout_reaps_a_live_worker_job_past_its_own_job_timeout() -> None:
    """
    The JOB-LEVEL watchdog predicate (the incident's exact fix): a RUNNING job on a LIVE worker whose
    total age exceeds its per-collection effective job timeout + grace is a candidate even though the
    heartbeat is FRESH — the condition ``list_stale`` can never catch (a fresh heartbeat vetoes it).
    Proven on the compiled SQL because the unit suite has no real Postgres.
    """
    captured: dict[str, object] = {}

    class _CapturingSession:
        async def execute(self, statement):
            captured["statement"] = statement
            result = MagicMock()
            result.all.return_value = []
            return result

    from shared_libs.services.db.postgresql.apis import JobApi  # noqa: PLC0415

    await JobApi.list_over_job_timeout(
        _CapturingSession(),
        default_job_timeout_seconds=1800.0,
        grace_seconds=300.0,
        heartbeat_stale_seconds=180,
    )

    sql = str(
        captured["statement"].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    ).lower()
    # RUNNING-only, and it needs a real start time to age from.
    assert "job.status = 'running'" in sql
    assert "job.started_at is not null" in sql
    # The effective job timeout is the per-COLLECTION override coalesced onto the global default — the
    # job timeout is the job's REAL job timeout, so a long-but-within-job timeout parse is never falsely reaped.
    assert "coalesce(collection.job_timeout_seconds, 1800.0)" in sql
    # DB-clock age cutoff: started_at older than now() - make_interval(job timeout + grace).
    assert "job.started_at < now() - make_interval" in sql
    # It joins the collection (for the job timeout) AND requires a FRESH heartbeat (inner join + last_seen
    # within the stale cutoff) — this path targets a LIVE worker, disjoint from list_stale's dead one.
    assert "join collection on collection.id = job.collection_id" in sql
    assert "join worker_heartbeats on worker_heartbeats.worker_id = job.worker_id" in sql
    assert "worker_heartbeats.last_seen >= now() - make_interval" in sql
    # TWO DB-clock cutoffs: the job timeout age cutoff on the job + the heartbeat freshness cutoff.
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
        # A dead worker heartbeat means the PROCESS is gone → attributed worker_killed (OOM-forward),
        # never auto-retried (the reaper marks FAILED terminal; the doc stays re-ingestable).
        assert call.kwargs["error_type"] == "worker_killed"
    # The operator-clear reason names the minutes and the presumed cause, and — because the reaper's
    # terminal status is FAILED — it must read like a REAP, never a "cancelled:" (that prefix belongs
    # to the CANCELLED cancel path; a failed chip carrying "cancelled:" is the contradiction QA caught).
    reason = mark_terminal.await_args_list[0].kwargs["reason"]
    assert "20m" in reason and "orphaned" in reason
    # The worker_killed reason is OOM-forward and actionable (the operator's levers).
    assert "out-of-memory" in reason and "WORKER_CONCURRENCY" in reason
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


async def test_reap_over_job_timeout_fails_each_wedged_job_with_job_timeout_exceeded(
    monkeypatch,
) -> None:
    """
    The JOB-LEVEL watchdog orchestration (the regression guard for the live incident): a RUNNING job
    on a LIVE worker (fresh heartbeat) past its job timeout is failed job_timeout_exceeded, its stage named in
    the reason and its document flagged FAILED — through the SAME _terminate path. list_over_job_timeout
    yields (job, effective_job_timeout) pairs so the reason can name the exceeded job timeout.
    """
    over_job_timeout = [
        (SimpleNamespace(id=uuid.uuid4(), document_id=uuid.uuid4(), current_stage="parse"), 900.0),
    ]
    doc_by_job = {job.id: job.document_id for job, _ in over_job_timeout}
    monkeypatch.setattr(
        facade_module.JobApi, "list_over_job_timeout", AsyncMock(return_value=over_job_timeout)
    )
    mark_terminal = AsyncMock(
        side_effect=lambda session, job_id, **kw: SimpleNamespace(
            id=job_id, document_id=doc_by_job[job_id]
        )
    )
    get_latest = AsyncMock(
        side_effect=lambda session, document_id: SimpleNamespace(
            id=next(job.id for job, _ in over_job_timeout if job.document_id == document_id)
        )
    )
    set_status = AsyncMock()
    monkeypatch.setattr(facade_module.JobApi, "mark_terminal", mark_terminal)
    monkeypatch.setattr(facade_module.JobApi, "get_latest_for_document", get_latest)
    monkeypatch.setattr(facade_module.DocumentApi, "set_status", set_status)

    facade = JobsFacade(_postgres_yielding(MagicMock()))
    reaped = await facade.reap_over_job_timeout(
        default_job_timeout_seconds=1800.0, grace_seconds=300.0, heartbeat_stale_seconds=180
    )

    job = over_job_timeout[0][0]
    assert reaped == [job.id]
    mark_terminal.assert_awaited_once()
    call = mark_terminal.await_args_list[0]
    assert call.kwargs["status"] == JobStatus.FAILED
    # Attributed job_timeout_exceeded — NOT worker_killed (the worker is alive) and NOT auto-retried.
    assert call.kwargs["error_type"] == "job_timeout_exceeded"
    reason = call.kwargs["reason"]
    # The reason names the wedged STAGE and the exceeded job timeout, reads like a REAP (never "cancelled:").
    assert "parse" in reason and "900s" in reason
    assert reason.startswith("reaped:")
    assert not reason.lower().startswith("cancelled")
    # The document is mirrored FAILED (re-ingestable).
    set_status.assert_awaited_once()
    assert set_status.await_args_list[0].args[2] == DocumentStatus.FAILED


async def test_reap_over_job_timeout_is_a_noop_when_nothing_is_over_job_timeout(
    monkeypatch,
) -> None:
    monkeypatch.setattr(facade_module.JobApi, "list_over_job_timeout", AsyncMock(return_value=[]))
    mark_terminal = AsyncMock()
    set_status = AsyncMock()
    monkeypatch.setattr(facade_module.JobApi, "mark_terminal", mark_terminal)
    monkeypatch.setattr(facade_module.DocumentApi, "set_status", set_status)

    facade = JobsFacade(_postgres_yielding(MagicMock()))
    reaped = await facade.reap_over_job_timeout(
        default_job_timeout_seconds=1800.0, grace_seconds=300.0, heartbeat_stale_seconds=180
    )

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
    *,
    enabled: bool,
    reap_stale: AsyncMock,
    reap_over_job_timeout: AsyncMock | None = None,
    prune: AsyncMock | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        RUNTIME_CONFIG=SimpleNamespace(
            WORKER_REAP_ENABLED=enabled,
            WORKER_REAP_STALE_SECONDS=1200,
            WORKER_PRUNE_STALE_SECONDS=180,
            WORKER_JOB_TIMEOUT_SECONDS=1800.0,
            WORKER_OVER_JOB_TIMEOUT_GRACE_SECONDS=300.0,
        ),
        database=SimpleNamespace(
            jobs=SimpleNamespace(
                reap_stale=reap_stale,
                reap_over_job_timeout=reap_over_job_timeout or AsyncMock(return_value=[]),
                prune_stale_heartbeats=prune or AsyncMock(return_value=[]),
            )
        ),
        logger=MagicMock(),
    )


async def test_reap_stuck_jobs_reaps_and_returns_ids_when_enabled(
    worker_jobs_modules, monkeypatch
) -> None:
    reaper = _reaper_module(worker_jobs_modules)
    killed_ids = [uuid.uuid4(), uuid.uuid4()]
    over_job_timeout_ids = [uuid.uuid4()]
    reap_stale = AsyncMock(return_value=killed_ids)
    reap_over_job_timeout = AsyncMock(return_value=over_job_timeout_ids)
    prune = AsyncMock(return_value=["worker-dead-1"])
    monkeypatch.setattr(
        reaper,
        "CONTEXT",
        _fake_context(
            enabled=True,
            reap_stale=reap_stale,
            reap_over_job_timeout=reap_over_job_timeout,
            prune=prune,
        ),
    )

    result = await reaper.reap_stuck_jobs({})

    # Dead-worker path: BOTH cutoffs — the silence threshold AND the heartbeat-veto cutoff (a fresh
    # heartbeat vetoes the reap), so it is called with (WORKER_REAP_STALE_SECONDS, WORKER_PRUNE_STALE_SECONDS).
    reap_stale.assert_awaited_once_with(1200, 180)
    # Job-level watchdog path: the default job timeout, the over-job timeout grace, and the SAME heartbeat cutoff
    # reap_stale uses (WORKER_PRUNE_STALE_SECONDS) so the fresh/stale boundary is shared — the two paths
    # stay disjoint (a job is a dead-worker orphan OR a live-worker wedge, never both).
    reap_over_job_timeout.assert_awaited_once_with(1800.0, 300.0, 180)
    # The reaper cron ALSO prunes crashed workers' stale heartbeats (moved off GET /workers/live).
    prune.assert_awaited_once_with(180)
    # The returned ids are the UNION of both reap paths (killed-worker first, over-job timeout appended).
    assert result == [str(job_id) for job_id in killed_ids + over_job_timeout_ids]


async def test_reap_stuck_jobs_is_a_noop_when_disabled(worker_jobs_modules, monkeypatch) -> None:
    reaper = _reaper_module(worker_jobs_modules)
    reap_stale = AsyncMock(return_value=[uuid.uuid4()])
    reap_over_job_timeout = AsyncMock(return_value=[uuid.uuid4()])
    prune = AsyncMock(return_value=[uuid.uuid4()])
    monkeypatch.setattr(
        reaper,
        "CONTEXT",
        _fake_context(
            enabled=False,
            reap_stale=reap_stale,
            reap_over_job_timeout=reap_over_job_timeout,
            prune=prune,
        ),
    )

    result = await reaper.reap_stuck_jobs({})

    assert result == []
    reap_stale.assert_not_awaited()
    # Neither reap condition nor the prune runs when disabled (the cron isn't registered; a direct
    # call is a full no-op).
    reap_over_job_timeout.assert_not_awaited()
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
# JobApi terminal transitions — the CONCURRENCY FIX (conditional UPDATE, wave A)
# --------------------------------------------------------------------------- #
#
# The live-worker watchdog (reap_over_job_timeout) can terminate a RUNNING job while its worker races to
# finish the SAME job, so the three terminal helpers are now DB-level CONDITIONAL UPDATEs guarded on
# the committed status (whoever commits first wins; the loser's WHERE matches nothing — a clean no-op,
# instead of overwriting a committed outcome off a stale identity-map row). These lock the guard on
# the compiled SQL so the ALWAYS-RUN unit suite ratchets it; the BEHAVIOURAL proof — that the guard
# actually no-ops the race against committed data — lives in the real-Postgres
# tests/db/test_jobs_terminal_transition_execution.py (a mock can't catch a WHERE-clause bug).


class _RecordingSession:
    """Captures every executed statement and hands back a preset result per call (rowcount / RETURNING
    row), so a helper's post-UPDATE branching can be steered without a real DB."""

    def __init__(self, results: list[object]) -> None:
        self._results = results
        self.statements: list[object] = []

    async def execute(self, statement):  # noqa: ANN001, ANN201
        self.statements.append(statement)
        return self._results[len(self.statements) - 1]


def _compiled(statement) -> str:  # noqa: ANN001
    """The statement compiled to literal Postgres SQL (lowercased) for substring assertions."""
    return str(
        statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    ).lower()


async def test_mark_done_is_a_conditional_update_guarded_on_running() -> None:
    """mark_done is an ``UPDATE job ... WHERE id = :id AND status = 'running'`` — never a blind write,
    so a late completion can never overwrite a job the reaper already made terminal."""
    import datetime as _dt  # noqa: PLC0415

    from shared_libs.services.db.postgresql.apis import JobApi  # noqa: PLC0415

    session = _RecordingSession([MagicMock()])
    await JobApi.mark_done(session, uuid.uuid4(), finished_at=_dt.datetime.now(_dt.UTC))

    sql = _compiled(session.statements[0])
    assert sql.startswith("update job set")
    assert "job.status = 'running'" in sql


async def test_mark_failed_guards_the_update_and_skips_stage_events_on_noop() -> None:
    """mark_failed's job UPDATE is guarded on status = 'running'; when it transitions NOTHING (rowcount
    0, a concurrent reap won), it must not touch the stage-event timeline — so only ONE statement runs."""
    import datetime as _dt  # noqa: PLC0415

    from shared_libs.services.db.postgresql.apis import JobApi  # noqa: PLC0415

    # rowcount 0 → the job was already terminal → the stage-event close must be skipped.
    session = _RecordingSession([SimpleNamespace(rowcount=0)])
    await JobApi.mark_failed(
        session, uuid.uuid4(), error="boom", finished_at=_dt.datetime.now(_dt.UTC)
    )

    assert len(session.statements) == 1  # the stage-event UPDATE was NOT issued
    sql = _compiled(session.statements[0])
    assert sql.startswith("update job set")
    assert "job.status = 'running'" in sql


async def test_mark_terminal_is_a_conditional_returning_update_admitting_pending() -> None:
    """mark_terminal is an ``UPDATE ... WHERE status IN ('pending', 'running') ... RETURNING``: it
    serializes on the row lock (RETURNING no-op when the job already went terminal) yet still admits a
    QUEUED (pending) job so a queued job can be force-cancelled before it ran. A None RETURNING row
    short-circuits before the stage-event close (only ONE statement runs)."""
    import datetime as _dt  # noqa: PLC0415

    from shared_libs.services.db.postgresql.apis import JobApi  # noqa: PLC0415

    # RETURNING yields no row → the transition was a no-op → the stage-event close is skipped.
    no_row = MagicMock()
    no_row.scalars.return_value.first.return_value = None
    session = _RecordingSession([no_row])
    returned = await JobApi.mark_terminal(
        session,
        uuid.uuid4(),
        status=JobStatus.FAILED,
        reason="reaped",
        finished_at=_dt.datetime.now(_dt.UTC),
        error_type="job_timeout_exceeded",
    )

    assert returned is None
    assert len(session.statements) == 1  # the stage-event UPDATE was NOT issued
    sql = _compiled(session.statements[0])
    assert sql.startswith("update job set")
    assert "job.status in ('pending', 'running')" in sql
    assert "returning" in sql


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
    assert "job.status = 'running'" in sql
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
