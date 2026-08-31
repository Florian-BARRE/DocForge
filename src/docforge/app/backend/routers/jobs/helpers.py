# ====== Code Summary ======
# WorkersLiveHelpers — the pure mapping behind GET /jobs/workers/live. It fuses two independent
# signals into one per-worker view: the worker_heartbeats table (liveness, incl. idle-but-alive
# workers) and the RUNNING job rows (what each worker is doing). Kept out of router.py so the route
# stays orchestration and the liveness logic is unit-testable against plain rows.

# ====== Standard Library Imports ======
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG

# ====== Local Project Imports ======
from .models import (
    JobStatus,
    WorkerActivity,
    WorkersLive,
)


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
            heartbeats (list[Any]): The worker_heartbeats rows (worker_id, last_seen, started_at).
            running_jobs (list[Any]): The RUNNING job rows (each carries worker_id + live state).
            allowed_collections (set[str] | None): Collection ids whose jobs may be surfaced, or None
                for unrestricted (full-access / wildcard) callers.
            now (datetime | None): The reference instant for staleness (defaults to now, UTC).

        Returns:
            WorkersLive: One WorkerActivity per known worker, ordered by worker id.
        """
        # 1. Index each worker's live jobs by worker id (unknown worker_id folds into "unknown"),
        #    dropping any job outside the caller's allowed collections so a scoped key sees only its
        #    own — the fleet-wide endpoint must never leak another tenant's job identifiers.
        reference = now or datetime.now(UTC)
        jobs_by_worker: dict[str, list[JobStatus]] = defaultdict(list)
        for job in running_jobs:
            if (
                allowed_collections is not None
                and str(job.collection_id) not in allowed_collections
            ):
                continue
            jobs_by_worker[job.worker_id or "unknown"].append(JobStatus.from_row(job))

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
                    alive=WorkersLiveHelpers._is_alive(last_seen, reference),
                    busy=bool(jobs),
                    last_seen=last_seen,
                    started_at=heartbeat.started_at if heartbeat is not None else None,
                    jobs=jobs,
                )
            )
        return WorkersLive(workers=workers)


__all__ = ["WorkersLiveHelpers"]
