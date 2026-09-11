# ====== Code Summary ======
# WorkersLiveHelpers — the pure mapping behind GET /jobs/workers/live. It fuses two independent
# signals into one per-worker view: the worker_heartbeats table (liveness, incl. idle-but-alive
# workers) and the RUNNING job rows (what each worker is doing). Kept out of router.py so the route
# stays orchestration and the liveness logic is unit-testable against plain rows.

# ====== Standard Library Imports ======
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

# ====== Third-Party Library Imports ======
from fastapi import HTTPException
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG
from shared_libs.services.db.postgresql.apis.job_api import (
    FailureAggregates,
    TimeseriesAggregates,
)
from shared_libs.services.db.postgresql.tables import JobStatus as JobStatusEnum

# ====== Local Project Imports ======
from ...libs.auth import AuthPrincipal, AuthzGuard
from .models import (
    CollectionFailureBucket,
    FailureBreakdown,
    FailureBucket,
    JobStatus,
    JobTimeseries,
    TimeseriesBucket,
    WorkerActivity,
    WorkersLive,
)

# The hourly bucket width of the trends series, in seconds — one place so the SQL truncation
# ("hour") and the reported ``bucket_seconds`` never drift apart.
_BUCKET_SECONDS = 3600


class CancelAction(StrEnum):
    """The state-machine decision for a cancel request — computed BEFORE any DB mutation."""

    # A queued (or force-targeted) job → terminate now (CANCELLED); the worker skips it at dequeue.
    TERMINATE = "terminate"
    # A running job, cooperative (force=false) → flag it to stop at its next stage boundary.
    REQUEST = "request"
    # A running job with force=true → force-terminate now regardless of worker state (wedged job).
    FORCE = "force"
    # A job already in a terminal state → nothing to cancel (the route answers 409).
    ALREADY_TERMINAL = "already_terminal"


class JobCancellationHelpers:
    """Static, store-free helpers deciding how a cancel request maps to a job's current state."""

    logger = loggerplusplus.bind(identifier="JobCancellationHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("JobCancellationHelpers is a static-only class and cannot be instantiated.")

    # The canonical terminal set lives on the enum so every consumer (here + the SSE stream) agrees.
    _TERMINAL = JobStatusEnum.terminal()

    @classmethod
    def decide(cls, status: JobStatusEnum, force: bool) -> CancelAction:
        """
        Map a job's current status (+ the force flag) to the cancel action to take — pure, no I/O.

        Deciding before touching the store keeps the route fail-fast (an already-terminal job is a
        409 before any mutation) and makes the state machine unit-testable in isolation.

        Args:
            status (JobStatusEnum): The job's current status.
            force (bool): The request's force flag (immediate terminate of a wedged running job).

        Returns:
            CancelAction: TERMINATE (queued/force-now), REQUEST (running cooperative), FORCE (running
                force) or ALREADY_TERMINAL (nothing to do).
        """
        # 1. A finished job cannot be cancelled — the route turns this into a 409.
        if status in cls._TERMINAL:
            return CancelAction.ALREADY_TERMINAL

        # 2. A queued job never started: terminate it now; the worker's dequeue guard skips it later.
        if status == JobStatusEnum.PENDING:
            return CancelAction.TERMINATE

        # 3. A running job: cooperative stop by default, immediate force-terminate when force=true.
        return CancelAction.FORCE if force else CancelAction.REQUEST


class WorkersLiveHelpers:
    """Static, store-free helpers assembling the live-workers view from heartbeats + running jobs."""

    logger = loggerplusplus.bind(identifier="WorkersLiveHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("WorkersLiveHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def _is_alive(last_seen: datetime | None, now: datetime) -> bool:
        """Whether a heartbeat is fresher than the liveness threshold (None → not alive)."""
        if last_seen is None:
            return False
        return (now - last_seen).total_seconds() <= RUNTIME_CONFIG.WORKER_ALIVE_THRESHOLD_SECONDS

    @staticmethod
    def assemble(
        heartbeats: list[Any],
        running_jobs: list[Any],
        allowed_collections: set[str] | None = None,
        now: datetime | None = None,
    ) -> WorkersLive:
        """
        Fuse heartbeat rows and RUNNING job rows into one liveness-aware workers view.

        Every worker that has EITHER a heartbeat OR a running job appears exactly once: ``alive`` is
        driven by heartbeat freshness (a worker with no heartbeat row is not alive), ``busy`` by
        owning a running job. An idle-but-alive worker (fresh heartbeat, no job) is therefore visible
        with ``alive=True, busy=False``; a worker whose heartbeat went stale reads ``alive=False``.

        Tenant isolation: ``allowed_collections`` restricts which running jobs are attached to (and
        counted towards ``busy`` for) each worker. ``None`` = unrestricted (a full-access / wildcard
        key sees every job); a concrete set means a scoped key sees ONLY its own collections' jobs, so
        this fleet-wide view never leaks another tenant's job/document/collection ids. Worker liveness
        (infra, not tenant data) is still shown for every worker.

        Args:
            heartbeats (list[Any]): The worker_heartbeats rows (worker_id, worker_name, last_seen,
                started_at).
            running_jobs (list[Any]): The RUNNING jobs as JobWithNames (job row + joined document
                filename + collection name); each job carries worker_id + live state.
            allowed_collections (set[str] | None): Collection ids whose jobs may be surfaced, or None
                for unrestricted (full-access / wildcard) callers.
            now (datetime | None): The reference instant for staleness (defaults to now, UTC).

        Returns:
            WorkersLive: One WorkerActivity per known worker, ordered by worker id.
        """
        # 1. Index each worker's live jobs by worker id (unknown worker_id folds into "unknown"),
        #    dropping any job outside the caller's allowed collections so a scoped key sees only its
        #    own — the fleet-wide endpoint must never leak another tenant's job identifiers. Each item
        #    is a JobWithNames (job row + joined document filename + collection name).
        reference = now or datetime.now(UTC)
        jobs_by_worker: dict[str, list[JobStatus]] = defaultdict(list)
        for entry in running_jobs:
            job = entry.job
            if (
                allowed_collections is not None
                and str(job.collection_id) not in allowed_collections
            ):
                continue
            jobs_by_worker[job.worker_id or "unknown"].append(
                JobStatus.from_row(
                    job,
                    entry.document_filename,
                    entry.collection_name,
                    document_title=getattr(entry, "document_title", None),
                )
            )

        # 2. Index the heartbeats by worker id — the liveness source of truth.
        heartbeat_by_worker = {hb.worker_id: hb for hb in heartbeats}

        # 3. The visible fleet is the union: every heartbeating worker + every worker running a job.
        worker_ids = sorted(set(heartbeat_by_worker) | set(jobs_by_worker))

        # 4. Build one activity per worker, fusing its heartbeat liveness with its running jobs.
        workers: list[WorkerActivity] = []
        for worker_id in worker_ids:
            heartbeat = heartbeat_by_worker.get(worker_id)
            last_seen = heartbeat.last_seen if heartbeat is not None else None
            jobs = jobs_by_worker.get(worker_id, [])
            workers.append(
                WorkerActivity(
                    worker_id=worker_id,
                    worker_name=getattr(heartbeat, "worker_name", None)
                    if heartbeat is not None
                    else None,
                    alive=WorkersLiveHelpers._is_alive(last_seen, reference),
                    busy=bool(jobs),
                    last_seen=last_seen,
                    started_at=heartbeat.started_at if heartbeat is not None else None,
                    max_jobs=getattr(heartbeat, "max_jobs", None)
                    if heartbeat is not None
                    else None,
                    cpu_percent=getattr(heartbeat, "cpu_percent", None)
                    if heartbeat is not None
                    else None,
                    mem_mb=getattr(heartbeat, "mem_mb", None) if heartbeat is not None else None,
                    mem_percent=getattr(heartbeat, "mem_percent", None)
                    if heartbeat is not None
                    else None,
                    jobs=jobs,
                )
            )
        return WorkersLive(workers=workers)


class JobScopeHelpers:
    """Static helper enforcing the fleet-wide-vs-scoped gate shared by every fleet job endpoint."""

    logger = loggerplusplus.bind(identifier="JobScopeHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("JobScopeHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def assert_fleet_or_scoped(principal: AuthPrincipal, collection_id: uuid.UUID | None) -> None:
        """
        Enforce the same scope gate ``GET /jobs`` and ``/jobs/queue`` apply to a fleet/scoped read.

        A named ``collection_id`` must pass the caller's collection scope (403 on a foreign one); an
        omitted one is a FLEET-WIDE read, allowed only for a full-access key — a collection-scoped key
        must name a collection it owns, so it can never read cross-tenant aggregates.

        Args:
            principal (AuthPrincipal): The authenticated caller.
            collection_id (uuid.UUID | None): The requested scope, or None for fleet-wide.

        Raises:
            HTTPException: 403 when a scoped key requests a fleet-wide read or a foreign collection.
        """
        # 1. A named collection is gated by the caller's own scope.
        if collection_id is not None:
            AuthzGuard.assert_collection_scope(principal, str(collection_id))
            return
        # 2. Fleet-wide is full-access only — a scoped key must name a collection it owns.
        if AuthzGuard.scoped_collections(principal) is not None:
            raise HTTPException(
                status_code=403,
                detail="collection_id is required for a collection-scoped key (fleet-wide job "
                "aggregates are restricted to full-access keys).",
            )


class FailureBreakdownHelpers:
    """Static helper mapping the data-layer failure aggregates into the response model."""

    logger = loggerplusplus.bind(identifier="FailureBreakdownHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "FailureBreakdownHelpers is a static-only class and cannot be instantiated."
        )

    @staticmethod
    def build(
        aggregates: FailureAggregates,
        collection_id: uuid.UUID | None,
        window_hours: int,
        since: datetime,
    ) -> FailureBreakdown:
        """
        Map the raw grouped counts into the ``FailureBreakdown`` response.

        A null group key (an unattributed error class or a missing stage) surfaces as the literal
        'unknown' so the UI never renders a blank bucket label.

        Args:
            aggregates (FailureAggregates): The three raw groupings + total from the data layer.
            collection_id (uuid.UUID | None): The scope echoed back (None = fleet-wide).
            window_hours (int): The window width echoed back.
            since (datetime): The window start echoed back.

        Returns:
            FailureBreakdown: The panel-ready breakdown.
        """
        return FailureBreakdown(
            collection_id=str(collection_id) if collection_id is not None else None,
            window_hours=window_hours,
            since=since,
            total_failed=aggregates.total,
            by_error_type=[
                FailureBucket(label=label or "unknown", count=count)
                for label, count in aggregates.by_error_type
            ],
            by_stage=[
                FailureBucket(label=label or "unknown", count=count)
                for label, count in aggregates.by_stage
            ],
            by_collection=[
                CollectionFailureBucket(
                    collection_id=str(coll_id), collection_name=name, count=count
                )
                for coll_id, name, count in aggregates.by_collection
            ],
        )


class JobTrendsHelpers:
    """Static helper turning the per-hour aggregates into contiguous sparkline buckets."""

    logger = loggerplusplus.bind(identifier="JobTrendsHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("JobTrendsHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def _floor_hour(moment: datetime) -> datetime:
        """Floor an instant to its UTC hour boundary (the canonical bucket key)."""
        return moment.astimezone(UTC).replace(minute=0, second=0, microsecond=0)

    @classmethod
    def assemble(
        cls,
        aggregates: TimeseriesAggregates,
        collection_id: uuid.UUID | None,
        window_hours: int,
        since: datetime,
        now: datetime | None = None,
    ) -> JobTimeseries:
        """
        Build contiguous ascending hourly buckets and reconstruct the backlog from the aggregates.

        The DB returns sparse hour rows (only hours with activity); this fills EVERY hour from the
        window start to the current hour so a sparkline has no gaps. Each hour's backlog is rebuilt
        as ``baseline + cumulative(arrivals) − cumulative(completions)`` at that hour's end (clamped at
        zero to absorb any drift from pruned history). All bucket keys are normalised to the UTC hour,
        so the deployment's database timezone never shifts a boundary.

        Args:
            aggregates (TimeseriesAggregates): The backlog baseline + arrival/completion hour buckets.
            collection_id (uuid.UUID | None): The scope echoed back (None = fleet-wide).
            window_hours (int): The window width echoed back.
            since (datetime): The window start (already hour-aligned by the caller).
            now (datetime | None): The reference end instant (defaults to now, UTC).

        Returns:
            JobTimeseries: The contiguous hourly series.
        """
        # 1. Index the sparse DB rows by their UTC hour key — arrivals, and completions split by status.
        arrivals: dict[datetime, int] = {
            cls._floor_hour(bucket): count for bucket, count in aggregates.arrivals
        }
        done: dict[datetime, int] = {}
        failed: dict[datetime, int] = {}
        for bucket, status, count in aggregates.completions:
            target = done if status == JobStatusEnum.DONE else failed
            target[cls._floor_hour(bucket)] = count

        # 2. Walk every hour from the window start to the current hour, accumulating the backlog.
        start = cls._floor_hour(since)
        end = cls._floor_hour(now or datetime.now(UTC))
        buckets: list[TimeseriesBucket] = []
        backlog = aggregates.baseline
        hour = start
        while hour <= end:
            created = arrivals.get(hour, 0)
            hour_done = done.get(hour, 0)
            hour_failed = failed.get(hour, 0)
            backlog += created - (hour_done + hour_failed)
            buckets.append(
                TimeseriesBucket(
                    bucket_start=hour,
                    created=created,
                    done=hour_done,
                    failed=hour_failed,
                    backlog=max(backlog, 0),
                )
            )
            hour += timedelta(hours=1)

        return JobTimeseries(
            collection_id=str(collection_id) if collection_id is not None else None,
            window_hours=window_hours,
            bucket_seconds=_BUCKET_SECONDS,
            buckets=buckets,
        )


__all__ = [
    "WorkersLiveHelpers",
    "JobCancellationHelpers",
    "CancelAction",
    "JobScopeHelpers",
    "FailureBreakdownHelpers",
    "JobTrendsHelpers",
]
