# ====== Code Summary ======
# JobDashboardApi — Dashboard aggregates over the job table: backlog depth, status histogram, last
# successful ingest times, the failure breakdown, new-failure signals and the hourly trend counts.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence
from datetime import datetime

# ====== Third-Party Library Imports ======
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from ...tables import (
    Collection,
    Job,
    JobKind,
    JobStatus,
)

# ====== Local Project Imports ======
from .job_api_models import FailureAggregates, TimeseriesAggregates


class JobDashboardApi:
    """Static data-access API: dashboard aggregates over the job table."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("JobDashboardApi is a static-only class and cannot be instantiated.")

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
    async def status_counts(session: AsyncSession) -> dict[JobStatus, int]:
        """
        Count all jobs grouped by status — the fleet-wide state histogram for /metrics gauges.

        One grouped count over the whole jobs table (every status, not just the backlog), so the
        pending / running / failed gauges come from a single round-trip.

        Args:
            session (AsyncSession): The active DB session.

        Returns:
            dict[JobStatus, int]: Job count per status (statuses with no rows are absent).
        """
        result = await session.execute(select(Job.status, func.count(Job.id)).group_by(Job.status))
        return {status: int(count) for status, count in result.all()}

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
                Job.kind != JobKind.REBUILD_INDEX,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def last_successful_ingest_at_by_collections(
        session: AsyncSession, collection_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, datetime]:
        """
        Return each collection's last successful ingest time in ONE grouped query (no N+1).

        The fleet-dashboard "last ingest" for every collection at once — a collection that has never
        completed an ingest is simply absent from the map (the caller defaults it to None).

        Args:
            session (AsyncSession): The active DB session.
            collection_ids (Sequence[uuid.UUID]): The collections to look up (empty → empty map).

        Returns:
            dict[uuid.UUID, datetime]: collection id → the latest DONE job's finish time.
        """
        # 1. Nothing to look up — skip the round-trip.
        if not collection_ids:
            return {}
        # 2. One GROUP BY over the DONE jobs — the whole fleet's last-ingest in a single scan.
        result = await session.execute(
            select(Job.collection_id, func.max(Job.finished_at))
            .where(
                Job.collection_id.in_(collection_ids),
                Job.status == JobStatus.DONE,
                Job.kind != JobKind.REBUILD_INDEX,
            )
            .group_by(Job.collection_id)
        )
        return {
            collection_id: finished_at
            for collection_id, finished_at in result.all()
            if finished_at is not None
        }

    @staticmethod
    async def failure_breakdown(
        session: AsyncSession,
        since: datetime,
        collection_id: uuid.UUID | None = None,
        top_n: int = 25,
    ) -> FailureAggregates:
        """
        Roll up FAILED jobs over a window into its three triage groupings (cause / stage / collection).

        The data behind the "why is it breaking" panel: failures created at or after ``since`` (the
        window, bounded by the ``ix_job_created_at`` index), optionally scoped to one collection. Each
        grouping is a separate GROUP BY ordered by descending count and capped to ``top_n`` so the
        dominant causes lead and an unbounded tail never bloats the response. Failures are attributed
        by the job's creation time (not its finish), which the leading created-at index serves cheaply.

        Args:
            session (AsyncSession): The active DB session.
            since (datetime): Window start — FAILED jobs created at/after this are aggregated.
            collection_id (uuid.UUID | None): Scope to one collection, or None for the whole fleet.
            top_n (int): Maximum buckets per grouping (the dominant causes).

        Returns:
            FailureAggregates: Total + the three descending, bounded groupings.
        """
        # 1. The shared base predicate: FAILED jobs inside the window, optionally one collection.
        base = [Job.status == JobStatus.FAILED, Job.created_at >= since]
        if collection_id is not None:
            base.append(Job.collection_id == collection_id)

        # 2. Total failures in the window (the panel's headline count).
        total = int(
            (await session.execute(select(func.count()).select_from(Job).where(*base))).scalar_one()
        )

        # 3. Cause roll-up (by structured exception class) and stage roll-up (the node it died in).
        by_error_type = [
            (value, int(count))
            for value, count in (
                await session.execute(
                    select(Job.error_type, func.count())
                    .where(*base)
                    .group_by(Job.error_type)
                    .order_by(func.count().desc())
                    .limit(top_n)
                )
            ).all()
        ]
        by_stage = [
            (value, int(count))
            for value, count in (
                await session.execute(
                    select(Job.current_stage, func.count())
                    .where(*base)
                    .group_by(Job.current_stage)
                    .order_by(func.count().desc())
                    .limit(top_n)
                )
            ).all()
        ]

        # 4. Collection roll-up — LEFT-joined to the name so a deleted collection still counts (name None).
        by_collection = [
            (coll_id, name, int(count))
            for coll_id, name, count in (
                await session.execute(
                    select(Job.collection_id, Collection.name, func.count())
                    .outerjoin(Collection, Collection.id == Job.collection_id)
                    .where(*base)
                    .group_by(Job.collection_id, Collection.name)
                    .order_by(func.count().desc())
                    .limit(top_n)
                )
            ).all()
        ]
        return FailureAggregates(
            total=total,
            by_error_type=by_error_type,
            by_stage=by_stage,
            by_collection=by_collection,
        )

    @staticmethod
    async def count_failed_since(
        session: AsyncSession, since: datetime, collection_id: uuid.UUID | None = None
    ) -> tuple[int, datetime | None]:
        """
        Count jobs that FAILED strictly after ``since`` and return the newest failure time.

        Backs the "X new failures since you last looked" signal: a job counts when it is FAILED and
        its ``finished_at`` (the instant it failed) is past the caller's last-seen cursor. The returned
        ``latest`` (max ``finished_at``) lets the client advance its cursor so the same failure is
        never counted twice. Keyed on ``finished_at`` so a job created before the cursor but failing
        after it is still caught (exactly the "new since" semantics a stale created-at filter would miss).

        Args:
            session (AsyncSession): The active DB session.
            since (datetime): The last-seen cursor — only failures finished strictly after it count.
            collection_id (uuid.UUID | None): Scope to one collection, or None for the whole fleet.

        Returns:
            tuple[int, datetime | None]: (new-failure count, newest failure ``finished_at`` or None).
        """
        conditions = [Job.status == JobStatus.FAILED, Job.finished_at > since]
        if collection_id is not None:
            conditions.append(Job.collection_id == collection_id)
        result = await session.execute(
            select(func.count(), func.max(Job.finished_at)).where(*conditions)
        )
        count, latest = result.one()
        return int(count), latest

    @staticmethod
    async def list_failed_since(
        session: AsyncSession,
        since: datetime,
        collection_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[uuid.UUID]:
        """
        Return the ids of jobs that FAILED after ``since``, newest failure first (bounded).

        The optional companion to ``count_failed_since`` when the caller wants the actual ids (to deep-
        link each new failure), bounded by ``limit`` so the signal never returns an unbounded list.

        Args:
            session (AsyncSession): The active DB session.
            since (datetime): Only failures finished strictly after this cursor.
            collection_id (uuid.UUID | None): Scope to one collection, or None for the whole fleet.
            limit (int): Maximum ids to return.

        Returns:
            list[uuid.UUID]: The new-failure job ids, newest failure first (at most ``limit``).
        """
        conditions = [Job.status == JobStatus.FAILED, Job.finished_at > since]
        if collection_id is not None:
            conditions.append(Job.collection_id == collection_id)
        result = await session.execute(
            select(Job.id).where(*conditions).order_by(Job.finished_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def job_timeseries(
        session: AsyncSession, since: datetime, collection_id: uuid.UUID | None = None
    ) -> TimeseriesAggregates:
        """
        Return the raw per-hour counts behind the trends sparklines — straight from the job table.

        Three cheap reads, no Prometheus: arrivals bucketed by ``date_trunc('hour', created_at)``,
        completions bucketed by ``date_trunc('hour', finished_at)`` split by terminal status, and the
        backlog BASELINE (jobs created before the window still un-finished at its start). The caller
        reconstructs each hour's backlog as ``baseline + cumulative(arrivals) - cumulative(completions)``
        — an instantaneous queued+running depth the job rows alone can express (hourly truncation is DB-
        clock but re-aligned to UTC hour boundaries by the caller, so deployment timezone is irrelevant).

        Args:
            session (AsyncSession): The active DB session.
            since (datetime): Window start — arrivals/completions at/after this hour are bucketed.
            collection_id (uuid.UUID | None): Scope to one collection, or None for the whole fleet.

        Returns:
            TimeseriesAggregates: The backlog baseline + the arrival and completion hour buckets.
        """
        # 1. Optional collection scope, shared by all three reads.
        scope = [] if collection_id is None else [Job.collection_id == collection_id]

        # 2. Arrivals per hour (created_at) — served by the leading ix_job_created_at index.
        arrivals_bucket = func.date_trunc("hour", Job.created_at)
        arrivals = [
            (bucket, int(count))
            for bucket, count in (
                await session.execute(
                    select(arrivals_bucket, func.count())
                    .where(Job.created_at >= since, *scope)
                    .group_by(arrivals_bucket)
                )
            ).all()
        ]

        # 3. Completions per hour (finished_at), split by terminal status → done/h and failed/h.
        completions_bucket = func.date_trunc("hour", Job.finished_at)
        completions = [
            (bucket, status, int(count))
            for bucket, status, count in (
                await session.execute(
                    select(completions_bucket, Job.status, func.count())
                    .where(
                        Job.finished_at >= since,
                        Job.status.in_([JobStatus.DONE, JobStatus.FAILED]),
                        *scope,
                    )
                    .group_by(completions_bucket, Job.status)
                )
            ).all()
        ]

        # 4. Backlog baseline: jobs created before the window still un-finished at its start (so the
        #    reconstructed per-bucket backlog never goes spuriously negative or starts from zero).
        baseline = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(Job)
                    .where(
                        Job.created_at < since,
                        or_(Job.finished_at.is_(None), Job.finished_at >= since),
                        *scope,
                    )
                )
            ).scalar_one()
        )
        return TimeseriesAggregates(baseline=baseline, arrivals=arrivals, completions=completions)


__all__ = ["JobDashboardApi"]
