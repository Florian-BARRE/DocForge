"""EXECUTES the job terminal-transition helpers (JobApi.mark_done / mark_failed / mark_terminal and
the JobsFacade._terminate document mirror) against a real Postgres — the concurrency fix from
worker-robustness wave A that a shape-only unit test can never prove.

Wave A added a live-worker watchdog (``reap_over_job_timeout``) that terminates a RUNNING job while its
worker races to finish the SAME job. The three terminal helpers were load-then-mutate guarded only by
an in-Python status check, which (a) could overwrite a committed outcome and (b) read a STALE row from
the reaper's own identity map. They are now DB-level CONDITIONAL UPDATEs guarded on the committed
status, so whoever commits first wins and the loser is a clean no-op. Only a real DB exercises the
``WHERE status = 'running'`` predicate and the ``RETURNING`` no-op — a mock cannot catch a WHERE bug,
which is exactly this defect's class.

Covered, end to end:
  * mark_done flips RUNNING→DONE, but is a NO-OP on an already-terminal (FAILED) job — the "reaper
    wrote first, worker finished second" race never resurrects a reaped FAILED job to DONE.
  * mark_terminal transitions a RUNNING (and a queued PENDING) job and RETURNs it; on an already-DONE
    job it returns None and leaves the row DONE — and through _terminate the fully-ingested document is
    NOT flipped to FAILED (the "worker finished first" race).
  * mark_failed closes the open stage-event row on a real transition, but leaves the timeline untouched
    when the job was already made terminal by a concurrent writer (rowcount 0).

Also covers the 0.22.1 side-job correctness fixes (a non-ingest ``metadata_sync`` row in the shared
ingest-oriented job table):
  * _terminate's KIND GATE — force-cancelling or reaping a metadata_sync side-job (which is the
    document's LATEST job, so the latest-owner guard alone would pass) terminates the JOB but leaves the
    healthy DONE document UNCHANGED; only an ingest termination mirrors document status.
  * abandon — a PENDING metadata_sync row whose enqueue failed is flipped FAILED (freeing the
    ``uq_job_active_per_document`` lock) so a subsequent create_metadata_sync no longer wedges.

Each test opens its own engine/session against the session-scoped migrated throwaway db and seeds its
own collection/document/job, so the tests are order-independent (every read is id-scoped).
"""

# ====== Standard Library Imports ======
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

# ====== Third-Party Library Imports ======
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# ====== Internal Project Imports ======
from shared_libs.services.db.facades import JobsFacade
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import JobApi
from shared_libs.services.db.postgresql.tables import (
    Collection,
    Document,
    DocumentStatus,
    Job,
    JobKind,
    JobStageEvent,
    JobStatus,
    SourceKind,
)

pytestmark = pytest.mark.db


@pytest.fixture
async def session(migrated_db_dsn: str) -> AsyncIterator[AsyncSession]:
    """A fresh engine + session per test against the head-migrated throwaway db."""
    engine = create_async_engine(migrated_db_dsn)
    try:
        async with AsyncSession(engine) as db_session:
            yield db_session
    finally:
        await engine.dispose()


async def _seed_job(
    db_session: AsyncSession,
    *,
    job_status: JobStatus,
    doc_status: DocumentStatus,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Seed one collection + document + job at the given statuses; return (job_id, document_id)."""
    # 1. A throwaway collection (unique name so parallel runs never collide).
    collection = Collection(
        name=f"terminal-txn-{uuid.uuid4().hex[:8]}",
        supported_formats=["pdf"],
        max_file_size_bytes=10_000_000,
    )
    db_session.add(collection)
    await db_session.flush()

    # 2. Its document, at the requested terminal/processing status.
    document = Document(
        collection_id=collection.id,
        source_hash=f"hash-{uuid.uuid4().hex}",
        filename="doc.pdf",
        format="pdf",
        mime_type="application/pdf",
        file_size=1024,
        source_kind=SourceKind.DIGITAL_BORN,
        status=doc_status,
        pipeline_version="v1",
    )
    db_session.add(document)
    await db_session.flush()

    # 3. The job, at the requested status; a started_at so an aged/running row is realistic.
    job = Job(
        document_id=document.id,
        collection_id=collection.id,
        status=job_status,
        started_at=datetime.now(UTC),
    )
    db_session.add(job)
    await db_session.flush()
    return job.id, document.id


async def _status_of(db_session: AsyncSession, job_id: uuid.UUID) -> JobStatus:
    """Read the job's CURRENT committed status straight from the DB (bypassing the identity map)."""
    db_session.expire_all()
    return await db_session.scalar(select(Job.status).where(Job.id == job_id))


# ── mark_done — RUNNING→DONE, but never resurrects a reaped FAILED job ──────────────────────────────


async def test_mark_done_completes_a_running_job(session: AsyncSession) -> None:
    """The happy path still works: a RUNNING job is completed to DONE with progress 100."""
    job_id, _ = await _seed_job(
        session, job_status=JobStatus.RUNNING, doc_status=DocumentStatus.PROCESSING
    )

    await JobApi.mark_done(session, job_id, finished_at=datetime.now(UTC))

    assert await _status_of(session, job_id) == JobStatus.DONE


async def test_mark_done_is_a_noop_on_an_already_failed_job(session: AsyncSession) -> None:
    """The 'reaper wrote first, worker finished second' race: a late mark_done on a job the reaper
    already marked FAILED must NOT flip it back to DONE — the conditional WHERE matches nothing."""
    job_id, _ = await _seed_job(
        session, job_status=JobStatus.FAILED, doc_status=DocumentStatus.FAILED
    )

    await JobApi.mark_done(session, job_id, finished_at=datetime.now(UTC))

    # Still FAILED — the reaped outcome is never overwritten by the trailing completion.
    assert await _status_of(session, job_id) == JobStatus.FAILED


# ── mark_terminal — conditional transition + RETURNING no-op ────────────────────────────────────────


async def test_mark_terminal_transitions_a_running_job_and_returns_it(
    session: AsyncSession,
) -> None:
    """The happy reaper path: a RUNNING job is transitioned to FAILED and the fresh row is returned."""
    job_id, doc_id = await _seed_job(
        session, job_status=JobStatus.RUNNING, doc_status=DocumentStatus.PROCESSING
    )

    returned = await JobApi.mark_terminal(
        session,
        job_id,
        status=JobStatus.FAILED,
        reason="reaped: over job timeout",
        finished_at=datetime.now(UTC),
        error_type="job_timeout_exceeded",
    )

    assert returned is not None
    assert returned.document_id == doc_id
    assert await _status_of(session, job_id) == JobStatus.FAILED


async def test_mark_terminal_cancels_a_queued_pending_job(session: AsyncSession) -> None:
    """A QUEUED (pending) job can still be force-cancelled before it ever ran — the guard admits
    pending as well as running, so this regression of the queued-cancel path is covered."""
    job_id, _ = await _seed_job(
        session, job_status=JobStatus.PENDING, doc_status=DocumentStatus.PENDING
    )

    returned = await JobApi.mark_terminal(
        session,
        job_id,
        status=JobStatus.CANCELLED,
        reason="cancelled while queued",
        finished_at=datetime.now(UTC),
    )

    assert returned is not None
    assert await _status_of(session, job_id) == JobStatus.CANCELLED


async def test_mark_terminal_is_a_noop_on_an_already_done_job(session: AsyncSession) -> None:
    """The 'worker finished first' race at the primitive: mark_terminal(FAILED) on a job already DONE
    returns None and leaves the row DONE — nothing to terminate on a finished job."""
    job_id, _ = await _seed_job(session, job_status=JobStatus.DONE, doc_status=DocumentStatus.DONE)

    returned = await JobApi.mark_terminal(
        session,
        job_id,
        status=JobStatus.FAILED,
        reason="reaped: over job timeout",
        finished_at=datetime.now(UTC),
        error_type="job_timeout_exceeded",
    )

    assert returned is None
    assert await _status_of(session, job_id) == JobStatus.DONE


async def test_terminate_does_not_flip_a_fully_ingested_document(
    migrated_db_dsn: str, session: AsyncSession
) -> None:
    """The user-visible incident: the live-worker watchdog reaping a job the worker JUST finished must
    NOT flip the fully-ingested document (chunks already in Qdrant + Postgres) to FAILED with a scary
    job timeout message. Because mark_terminal now returns None on the already-DONE job, _terminate skips
    the document mirror entirely — the document stays DONE."""
    job_id, doc_id = await _seed_job(
        session, job_status=JobStatus.DONE, doc_status=DocumentStatus.DONE
    )

    client = PostgresClient(migrated_db_dsn)
    try:
        facade = JobsFacade(client)
        returned = await facade._terminate(
            session,
            job_id,
            job_status=JobStatus.FAILED,
            doc_status=DocumentStatus.FAILED,
            reason="reaped: over job timeout",
            error_type="job_timeout_exceeded",
        )
    finally:
        await client.dispose()

    # No transition happened, and the fully-ingested document is untouched (still DONE, not FAILED).
    assert returned is None
    doc_status = await session.scalar(select(Document.status).where(Document.id == doc_id))
    assert doc_status == DocumentStatus.DONE
    assert await _status_of(session, job_id) == JobStatus.DONE


# ── _terminate kind gate — terminating a metadata_sync side-job never writes DOCUMENT status ─────────


async def _seed_side_job_over_done_document(
    db_session: AsyncSession, *, worker_id: str | None = None
) -> tuple[uuid.UUID, uuid.UUID]:
    """Seed a DONE document owned by a terminal INGEST job, then a live ``metadata_sync`` side-job that
    is the document's LATEST job (the trap: the latest-owner guard alone would pass). Commits so a
    facade on its own connection sees the rows. Returns (metadata_sync_job_id, document_id)."""
    # 1. Collection + a fully-ingested (DONE) document.
    collection = Collection(
        name=f"kind-gate-{uuid.uuid4().hex[:8]}",
        supported_formats=["pdf"],
        max_file_size_bytes=10_000_000,
    )
    db_session.add(collection)
    await db_session.flush()
    document = Document(
        collection_id=collection.id,
        source_hash=f"hash-{uuid.uuid4().hex}",
        filename="doc.pdf",
        format="pdf",
        mime_type="application/pdf",
        file_size=1024,
        source_kind=SourceKind.DIGITAL_BORN,
        status=DocumentStatus.DONE,
        pipeline_version="v1",
    )
    db_session.add(document)
    await db_session.flush()

    # 2. The terminal INGEST run that produced the IR — an EARLIER row (explicit created_at so the
    #    side-job below is unambiguously the document's latest, independent of UUID tiebreaks).
    base = datetime.now(UTC)
    ingest = Job(
        document_id=document.id,
        collection_id=collection.id,
        kind=JobKind.INGEST,
        status=JobStatus.DONE,
        created_at=base - timedelta(minutes=5),
        started_at=base - timedelta(minutes=5),
        finished_at=base - timedelta(minutes=4),
    )
    db_session.add(ingest)
    await db_session.flush()

    # 3. The live metadata_sync side-job minted AFTER the ingest — the document's LATEST job.
    side = Job(
        document_id=document.id,
        collection_id=collection.id,
        kind=JobKind.METADATA_SYNC,
        status=JobStatus.RUNNING,
        worker_id=worker_id,
        created_at=base,
        started_at=base,
    )
    db_session.add(side)
    await db_session.flush()
    # Capture the plain UUIDs BEFORE commit: commit expires the ORM objects, so a later attribute
    # access would trigger a sync lazy-load outside the async greenlet (MissingGreenlet).
    side_id, document_id = side.id, document.id
    await db_session.commit()
    return side_id, document_id


async def test_force_terminate_metadata_sync_does_not_flip_the_document(
    migrated_db_dsn: str, session: AsyncSession
) -> None:
    """Finding 1 (cancel path): force-cancelling a metadata_sync side-job terminates the JOB but must
    leave its healthy DONE document untouched — the side-job is the document's latest job, so without
    the kind gate the latest-owner guard would pass and flip the DONE document to CANCELLED."""
    side_job_id, doc_id = await _seed_side_job_over_done_document(session)

    client = PostgresClient(migrated_db_dsn)
    try:
        facade = JobsFacade(client)
        returned = await facade.force_terminate(side_job_id, reason="manual cancel")
    finally:
        await client.dispose()

    # (a) The side-job row IS terminated (it genuinely is over; terminating frees the active lock).
    assert returned is not None
    assert await _status_of(session, side_job_id) == JobStatus.CANCELLED
    # (b) The DOCUMENT is UNCHANGED — still DONE, never clobbered to CANCELLED.
    session.expire_all()
    assert (
        await session.scalar(select(Document.status).where(Document.id == doc_id))
        == DocumentStatus.DONE
    )


async def test_reclaim_metadata_sync_does_not_flip_the_document(
    migrated_db_dsn: str, session: AsyncSession
) -> None:
    """Finding 1 (reaper path): the worker-restart reclaim failing a leftover RUNNING metadata_sync job
    must fail only the JOB, never its DONE document — same kind gate, through the reaper code path."""
    worker_id = f"worker-{uuid.uuid4().hex[:8]}"
    side_job_id, doc_id = await _seed_side_job_over_done_document(session, worker_id=worker_id)

    client = PostgresClient(migrated_db_dsn)
    try:
        facade = JobsFacade(client)
        reclaimed = await facade.reclaim_worker_jobs(worker_id)
    finally:
        await client.dispose()

    # (a) The side-job row was reclaimed to FAILED.
    assert side_job_id in reclaimed
    assert await _status_of(session, side_job_id) == JobStatus.FAILED
    # (b) The DOCUMENT is UNCHANGED — still DONE, never clobbered to FAILED.
    session.expire_all()
    assert (
        await session.scalar(select(Document.status).where(Document.id == doc_id))
        == DocumentStatus.DONE
    )


async def test_abandon_fails_a_pending_side_job_and_frees_the_active_lock(
    migrated_db_dsn: str, session: AsyncSession
) -> None:
    """Finding 2: a metadata_sync row whose enqueue failed must be abandoned — ``abandon`` flips the
    PENDING row to FAILED (mark_terminal admits pending) so it leaves the ``uq_job_active_per_document``
    predicate, and a subsequent ``create_metadata_sync`` for the same document succeeds instead of
    hitting the unique violation (the wedge the orphaned PENDING row would otherwise cause)."""
    # 1. A collection + a document, seeded + committed so the facade's own connection sees them.
    collection = Collection(
        name=f"abandon-{uuid.uuid4().hex[:8]}",
        supported_formats=["pdf"],
        max_file_size_bytes=10_000_000,
    )
    session.add(collection)
    await session.flush()
    document = Document(
        collection_id=collection.id,
        source_hash=f"hash-{uuid.uuid4().hex}",
        filename="doc.pdf",
        format="pdf",
        mime_type="application/pdf",
        file_size=1024,
        source_kind=SourceKind.DIGITAL_BORN,
        status=DocumentStatus.DONE,
        pipeline_version="v1",
    )
    session.add(document)
    await session.flush()
    # Capture the ids BEFORE commit (commit expires the ORM objects — a later ``.id`` would lazy-load
    # synchronously outside the async greenlet).
    document_id, collection_id = document.id, collection.id
    await session.commit()

    client = PostgresClient(migrated_db_dsn)
    try:
        facade = JobsFacade(client)
        # 2. Pre-create the tracked metadata_sync row (the enqueue then "fails"), and abandon it.
        orphan_id = await facade.create_metadata_sync(document_id, collection_id)
        await facade.abandon(orphan_id, reason="enqueue failed")
        # 3. The lock is free — a fresh create_metadata_sync must not hit the unique violation.
        second_id = await facade.create_metadata_sync(document_id, collection_id)
    finally:
        await client.dispose()

    # The orphan is terminal (FAILED, outside the active predicate); the second row is live.
    assert await _status_of(session, orphan_id) == JobStatus.FAILED
    assert await _status_of(session, second_id) == JobStatus.PENDING
    # The DOCUMENT was never touched by the side-job termination.
    session.expire_all()
    assert (
        await session.scalar(select(Document.status).where(Document.id == document_id))
        == DocumentStatus.DONE
    )


# ── mark_failed — closes the open stage row only on a real transition ───────────────────────────────


async def _open_stage_event(db_session: AsyncSession, job_id: uuid.UUID) -> uuid.UUID:
    """Add an OPEN (finished_at IS NULL) stage-event row for the job; return its id."""
    event = JobStageEvent(job_id=job_id, stage="parse", status="running")
    db_session.add(event)
    await db_session.flush()
    return event.id


async def test_mark_failed_closes_the_open_stage_row_on_a_running_job(
    session: AsyncSession,
) -> None:
    """The normal node-failure path: a RUNNING job is failed and its currently-open stage row is
    closed as failed (the silent-gap guard)."""
    job_id, _ = await _seed_job(
        session, job_status=JobStatus.RUNNING, doc_status=DocumentStatus.PROCESSING
    )
    event_id = await _open_stage_event(session, job_id)

    await JobApi.mark_failed(session, job_id, error="boom", finished_at=datetime.now(UTC))

    assert await _status_of(session, job_id) == JobStatus.FAILED
    session.expire_all()
    row = await session.scalar(select(JobStageEvent).where(JobStageEvent.id == event_id))
    assert row.status == "failed" and row.finished_at is not None


async def test_mark_failed_leaves_stage_events_untouched_when_already_terminal(
    session: AsyncSession,
) -> None:
    """The race guard: mark_failed on a job a concurrent writer already made terminal (here CANCELLED)
    is a full no-op — the WHERE matches nothing (rowcount 0), so it must NOT reopen/rewrite the open
    stage-event row (which belongs to whoever won the transition)."""
    job_id, _ = await _seed_job(
        session, job_status=JobStatus.CANCELLED, doc_status=DocumentStatus.CANCELLED
    )
    event_id = await _open_stage_event(session, job_id)

    await JobApi.mark_failed(session, job_id, error="boom", finished_at=datetime.now(UTC))

    # The job stayed CANCELLED and its open stage row was NOT touched (still running / open).
    assert await _status_of(session, job_id) == JobStatus.CANCELLED
    session.expire_all()
    row = await session.scalar(select(JobStageEvent).where(JobStageEvent.id == event_id))
    assert row.status == "running" and row.finished_at is None
