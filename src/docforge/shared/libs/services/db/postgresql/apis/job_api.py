# ====== Code Summary ======
# JobApi — the data-access API for ingestion observability: the job record and its per-stage event
# timeline. The job LIFECYCLE is expressed as explicit transitions (mark_running / set_progress /
# mark_done / mark_failed) rather than a generic patch — mark_running is retry-safe and clears the
# previous attempt's error/finish state, which a None-means-skip patch could never reset. And
# `record_event` appends to the stage timeline the live-status UI reads.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

# ====== Third-Party Library Imports ======
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from ..tables import Job, JobStageEvent, JobStatus, WorkerHeartbeat


class JobApi:
    """Static data-access API for ingestion jobs and their stage timeline."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("JobApi is a static-only class and cannot be instantiated.")

    @staticmethod
    async def create(session: AsyncSession, job: Job) -> Job:
        """Insert a job and return it (flushed)."""
        session.add(job)
        await session.flush()
        return job

    @staticmethod
    async def get(session: AsyncSession, job_id: uuid.UUID) -> Job | None:
        """Fetch a job by id, or None."""
        return await session.get(Job, job_id)

    @staticmethod
    async def mark_running(
        session: AsyncSession,
        job_id: uuid.UUID,
        worker_id: str,
        attempt: int,
        started_at: datetime,
    ) -> None:
        """Claim the job for a worker — retry-safe: clears the previous attempt's outcome."""
        job = await session.get(Job, job_id)
        if job is None:
            return
        job.status = JobStatus.RUNNING
        job.worker_id = worker_id
        job.attempt = attempt
        job.started_at = started_at
        # Reset the previous attempt's state so the UI never shows a stale error on a running job.
        job.error = None
        job.finished_at = None
        job.current_stage = None
        job.progress = 0

    @staticmethod
    async def set_progress(
        session: AsyncSession, job_id: uuid.UUID, current_stage: str, progress: int
    ) -> None:
        """Report the stage the worker is in and its coarse 0-100 progress."""
        job = await session.get(Job, job_id)
        if job is None:
            return
        job.current_stage = current_stage
        job.progress = progress

    @staticmethod
    async def set_items(
        session: AsyncSession,
        job_id: uuid.UUID,
        items_done: int | None,
        items_total: int | None,
    ) -> None:
        """
        Set the per-item counter for the CURRENT fan-out (foreach) root stage.

        Both values are written verbatim, so passing ``None``/``None`` is the explicit reset the
        worker uses when the job leaves a fan-out stage — a plain "None means skip" patch could
        never clear a stale counter.

        Args:
            session (AsyncSession): The active DB session.
            job_id (uuid.UUID): The job whose counter advances.
            items_done (int | None): Items finished so far (None outside a fan-out).
            items_total (int | None): Fan-out width (None outside a fan-out / until known).
        """
        job = await session.get(Job, job_id)
        if job is None:
            return
        job.items_done = items_done
        job.items_total = items_total

    @staticmethod
    async def mark_done(session: AsyncSession, job_id: uuid.UUID, finished_at: datetime) -> None:
        """Complete the job successfully."""
        job = await session.get(Job, job_id)
        if job is None:
            return
        job.status = JobStatus.DONE
        job.progress = 100
        job.finished_at = finished_at

    @staticmethod
    async def mark_failed(
        session: AsyncSession,
        job_id: uuid.UUID,
        error: str,
        finished_at: datetime,
        failed_node_id: str | None = None,
        failed_node_kind: str | None = None,
        failed_item_index: int | None = None,
        error_type: str | None = None,
    ) -> None:
        """
        Fail the job with its free-text error AND the structured failure breadcrumb.

        Also closes the job's currently-OPEN stage-event row (``finished_at IS NULL``) as failed, so
        a run cut mid-stage — a wall-clock timeout, a hard cancel or the reaper — leaves a red row on
        the exact stage it died in rather than an all-green trace with a silent gap. A normal node
        failure has already finalized its own stage row (via the END event), so this find-open update
        simply matches nothing and is a no-op.

        Args:
            session (AsyncSession): The active DB session.
            job_id (uuid.UUID): The job to fail.
            error (str): The free-text error message (the human-readable reason).
            finished_at (datetime): When the job ended.
            failed_node_id (str | None): The deepest node that raised.
            failed_node_kind (str | None): That node's kind.
            failed_item_index (int | None): The fan-out item index the failure sits in (None outside).
            error_type (str | None): The exception class name (e.g. "TimeoutError").
        """
        job = await session.get(Job, job_id)
        if job is None:
            return
        job.status = JobStatus.FAILED
        job.error = error
        job.finished_at = finished_at
        job.failed_node_id = failed_node_id
        job.failed_node_kind = failed_node_kind
        job.failed_item_index = failed_item_index
        job.error_type = error_type
        await session.execute(
            update(JobStageEvent)
            .where(JobStageEvent.job_id == job_id, JobStageEvent.finished_at.is_(None))
            .values(status="failed", finished_at=finished_at, detail=error)
        )

    @staticmethod
    async def record_event(session: AsyncSession, event: JobStageEvent) -> JobStageEvent:
        """Append a stage event to the job's timeline and return it (flushed, id assigned)."""
        session.add(event)
        await session.flush()
        return event

    @staticmethod
    async def finalize_event(
        session: AsyncSession,
        event_id: uuid.UUID,
        status: str,
        finished_at: datetime,
        detail: str | None,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        cost_usd: Decimal | None,
    ) -> None:
        """
        Close an OPEN stage-event row (opened at the stage's START) with its outcome.

        The stage timeline now writes a "running" row on START and finalizes it here on END, so a
        run cut before END leaves the row visibly open (later closed as failed by ``mark_failed``).

        Args:
            session (AsyncSession): The active DB session.
            event_id (uuid.UUID): The open row's id.
            status (str): Final status (success / skipped / failed).
            finished_at (datetime): When the stage ended.
            detail (str | None): Duration or error detail.
            prompt_tokens (int | None): Paid input tokens for the stage (None if no paid call).
            completion_tokens (int | None): Paid output tokens for the stage.
            cost_usd (Decimal | None): USD cost (None when unpriced).
        """
        await session.execute(
            update(JobStageEvent)
            .where(JobStageEvent.id == event_id)
            .values(
                status=status,
                finished_at=finished_at,
                detail=detail,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost_usd,
            )
        )

    @staticmethod
    async def upsert_heartbeat(
        session: AsyncSession, worker_id: str, last_seen: datetime, started_at: datetime
    ) -> None:
        """
        Register/refresh a worker's liveness row (keyed by its stable worker id).

        Upsert so a worker's first tick inserts and every later tick updates ``last_seen`` in place;
        ``started_at`` is refreshed too, so a same-hostname restart reports the NEW process uptime.

        Args:
            session (AsyncSession): The active DB session.
            worker_id (str): The worker's stable id (its hostname).
            last_seen (datetime): This tick's timestamp — its age is the liveness signal.
            started_at (datetime): When THIS worker process registered.
        """
        statement = pg_insert(WorkerHeartbeat).values(
            worker_id=worker_id, last_seen=last_seen, started_at=started_at
        )
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[WorkerHeartbeat.worker_id],
                set_={"last_seen": last_seen, "started_at": started_at},
            )
        )

    @staticmethod
    async def delete_heartbeat(session: AsyncSession, worker_id: str) -> None:
        """
        Remove a worker's liveness row — its graceful de-registration on clean shutdown.

        A cleanly-stopped worker deletes its own row so it vanishes from the fleet immediately,
        instead of lingering as a stale "off" card until it ages past the prune cutoff.

        Args:
            session (AsyncSession): The active DB session.
            worker_id (str): The stable id of the worker de-registering itself.
        """
        await session.execute(delete(WorkerHeartbeat).where(WorkerHeartbeat.worker_id == worker_id))

    @staticmethod
    async def prune_stale_heartbeats(session: AsyncSession, older_than_seconds: float) -> list[str]:
        """
        Delete heartbeat rows not refreshed within the cutoff — the crashed-worker sweep.

        A worker that dies without a clean shutdown never deletes its own row, so its heartbeat
        simply stops ageing forward. This removes any row whose ``last_seen`` froze past the cutoff,
        so a crashed worker eventually disappears from the fleet instead of accumulating forever.

        The comparison is genuinely cross-clock: the cutoff is the DATABASE clock (``func.now()``)
        while ``last_seen`` was written on the WORKER's Python clock (see ``HeartbeatWriter``). On the
        single-host compose deployment both share the host clock so skew ≈ 0; the wide margin between
        this prune cutoff and the alive threshold absorbs any normal drift, and a live worker's next
        beat (every ~10s) immediately refreshes ``last_seen`` — so a merely-drifted live worker is
        not pruned, and even if one were, it reappears on its next tick. Keep the cutoff well above
        the alive threshold so a live worker that missed a couple of beats is never deleted.

        Args:
            session (AsyncSession): The active DB session.
            older_than_seconds (float): A heartbeat older than this (by the DB clock) is pruned.

        Returns:
            list[str]: The worker ids removed (empty when nothing was stale).
        """
        result = await session.execute(
            delete(WorkerHeartbeat)
            .where(WorkerHeartbeat.last_seen < func.now() - timedelta(seconds=older_than_seconds))
            .returning(WorkerHeartbeat.worker_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def add_usage(
        session: AsyncSession,
        job_id: uuid.UUID,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float | None,
    ) -> None:
        """
        Atomically fold a stage's token/cost usage into the job's running per-document totals.

        Null-safe: an unknown-model stage (``cost_usd=None``) still adds its tokens but zero cost,
        so an unpriceable call never fabricates a number. Done as an in-place ``UPDATE ... SET col =
        col + :delta`` so concurrent stage ends never lose an increment.

        Args:
            session (AsyncSession): The active DB session.
            job_id (uuid.UUID): The job whose meter advances.
            prompt_tokens (int): Input tokens to add.
            completion_tokens (int): Output tokens to add.
            cost_usd (float | None): USD cost to add (None contributes 0).
        """
        cost = Decimal(str(cost_usd)) if cost_usd is not None else Decimal(0)
        await session.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(
                total_prompt_tokens=Job.total_prompt_tokens + prompt_tokens,
                total_completion_tokens=Job.total_completion_tokens + completion_tokens,
                cost_usd=Job.cost_usd + cost,
            )
        )

    @staticmethod
    async def avg_stage_durations(
        session: AsyncSession, collection_id: uuid.UUID
    ) -> dict[str, float]:
        """
        Average per-stage wall-clock duration (seconds) over the collection's DONE jobs.

        Feeds the UI's remaining-time estimate for a running job (it sums the not-yet-finished
        stages). Only events with BOTH timestamps count; a stage with no completed sample is absent.

        Args:
            session (AsyncSession): The active DB session.
            collection_id (uuid.UUID): The collection whose jobs' events are averaged.

        Returns:
            dict[str, float]: Stage id → average duration in seconds.
        """
        result = await session.execute(
            select(
                JobStageEvent.stage,
                func.avg(
                    func.extract("epoch", JobStageEvent.finished_at - JobStageEvent.started_at)
                ),
            )
            .join(Job, Job.id == JobStageEvent.job_id)
            .where(
                Job.collection_id == collection_id,
                Job.status == JobStatus.DONE,
                JobStageEvent.started_at.is_not(None),
                JobStageEvent.finished_at.is_not(None),
            )
            .group_by(JobStageEvent.stage)
        )
        return {stage: float(avg) for stage, avg in result.all() if avg is not None}

    @staticmethod
    async def collection_cost(
        session: AsyncSession, collection_id: uuid.UUID
    ) -> tuple[int, int, float, int]:
        """
        Roll up the collection's per-document meters into one total.

        Args:
            session (AsyncSession): The active DB session.
            collection_id (uuid.UUID): The collection to total.

        Returns:
            tuple[int, int, float, int]: (total prompt tokens, total completion tokens, total USD
                cost, document/job count) — all zero for a collection with no jobs.
        """
        result = await session.execute(
            select(
                func.coalesce(func.sum(Job.total_prompt_tokens), 0),
                func.coalesce(func.sum(Job.total_completion_tokens), 0),
                func.coalesce(func.sum(Job.cost_usd), 0),
                func.count(Job.id),
            ).where(Job.collection_id == collection_id)
        )
        prompt, completion, cost, count = result.one()
        return int(prompt), int(completion), float(cost), int(count)

    @staticmethod
    async def list_events(session: AsyncSession, job_id: uuid.UUID) -> list[JobStageEvent]:
        """Return a job's per-node trace, in execution order."""
        result = await session.execute(
            select(JobStageEvent)
            .where(JobStageEvent.job_id == job_id)
            .order_by(JobStageEvent.created_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_active(session: AsyncSession) -> list[Job]:
        """Return every RUNNING job — the live view of what the workers are doing."""
        result = await session.execute(
            select(Job).where(Job.status == JobStatus.RUNNING).order_by(Job.started_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_heartbeats(session: AsyncSession) -> list[WorkerHeartbeat]:
        """Return every worker heartbeat row, ordered by worker id — the fleet liveness snapshot."""
        result = await session.execute(
            select(WorkerHeartbeat).order_by(WorkerHeartbeat.worker_id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def queue_depth(
        session: AsyncSession, collection_id: uuid.UUID | None = None
    ) -> tuple[int, int]:
        """
        Count the backlog: pending (queued, unclaimed) and running jobs.

        Fleet-wide when ``collection_id`` is None, otherwise scoped to that collection. Done as one
        grouped count so both numbers come from a single round-trip.

        Args:
            session (AsyncSession): The active DB session.
            collection_id (uuid.UUID | None): Scope to one collection, or None for the whole fleet.

        Returns:
            tuple[int, int]: (pending count, running count) — both zero when nothing is queued.
        """
        conditions = [Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING])]
        if collection_id is not None:
            conditions.append(Job.collection_id == collection_id)
        result = await session.execute(
            select(Job.status, func.count(Job.id)).where(*conditions).group_by(Job.status)
        )
        counts = {status: int(count) for status, count in result.all()}
        return counts.get(JobStatus.PENDING, 0), counts.get(JobStatus.RUNNING, 0)

    @staticmethod
    async def list_stale(session: AsyncSession, older_than_seconds: float) -> list[Job]:
        """
        Return RUNNING jobs whose ``updated_at`` froze past the threshold — the reap candidates.

        The cutoff uses the DATABASE clock (``func.now()``) rather than Python's, so a clock skew
        between a worker and Postgres can never mis-classify a live job as stale. ``updated_at``
        bumps on every progress/stage write (TimestampedMixin ``onupdate``), so a frozen value is
        exactly the orphaned/wedged signal. PENDING (queued, not yet started) rows are excluded.

        Args:
            session (AsyncSession): The active DB session.
            older_than_seconds (float): A RUNNING job idle longer than this is stale.

        Returns:
            list[Job]: The stale RUNNING jobs, oldest ``updated_at`` first.
        """
        result = await session.execute(
            select(Job)
            .where(
                Job.status == JobStatus.RUNNING,
                Job.updated_at < func.now() - timedelta(seconds=older_than_seconds),
            )
            .order_by(Job.updated_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def last_successful_ingest_at(
        session: AsyncSession, collection_id: uuid.UUID
    ) -> datetime | None:
        """
        Return the ``finished_at`` of the collection's most recent DONE ingest job, or None.

        Every job is one document's ingestion, so the newest DONE ``finished_at`` is the collection's
        last successful indexing — the "last ingest" timestamp the health surface shows. None when the
        collection has never completed an ingest.

        Args:
            session (AsyncSession): The active DB session.
            collection_id (uuid.UUID): The collection whose last successful ingest is queried.

        Returns:
            datetime | None: The latest DONE job's finish time, or None when there is none.
        """
        result = await session.execute(
            select(func.max(Job.finished_at)).where(
                Job.collection_id == collection_id,
                Job.status == JobStatus.DONE,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_collection(session: AsyncSession, collection_id: uuid.UUID) -> list[Job]:
        """Return a collection's jobs, newest first."""
        result = await session.execute(
            select(Job).where(Job.collection_id == collection_id).order_by(Job.created_at.desc())
        )
        return list(result.scalars().all())


__all__ = ["JobApi"]
