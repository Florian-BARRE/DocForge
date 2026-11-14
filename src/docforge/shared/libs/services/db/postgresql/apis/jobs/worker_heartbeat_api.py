# ====== Code Summary ======
# WorkerHeartbeatApi — Worker liveness: upsert / delete / prune the heartbeat rows, list the fleet
# snapshot, and find the RUNNING jobs a restarted worker left behind (reclaim).

# ====== Standard Library Imports ======
from datetime import datetime, timedelta

# ====== Third-Party Library Imports ======
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from ...tables import (
    Job,
    JobStatus,
    WorkerHeartbeat,
)


class WorkerHeartbeatApi:
    """Static data-access API: worker liveness rows and the restart reclaim read."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("WorkerHeartbeatApi is a static-only class and cannot be instantiated.")

    @staticmethod
    async def upsert_heartbeat(
        session: AsyncSession,
        worker_id: str,
        worker_name: str,
        last_seen: datetime,
        started_at: datetime,
        max_jobs: int | None = None,
        cpu_percent: float | None = None,
        mem_mb: float | None = None,
        mem_percent: float | None = None,
    ) -> None:
        """
        Register/refresh a worker's liveness row (keyed by its stable worker id).

        Upsert so a worker's first tick inserts and every later tick updates ``last_seen`` in place;
        ``started_at``, ``worker_name``, ``max_jobs`` and the resource samples are refreshed too, so a
        same-hostname restart reports the NEW process uptime, any changed friendly name, its current
        capacity and its live CPU/memory.

        Args:
            session (AsyncSession): The active DB session.
            worker_id (str): The worker's stable id (its hostname).
            worker_name (str): The worker's friendly display name (WORKER_NAME, defaults to hostname).
            last_seen (datetime): This tick's timestamp — its age is the liveness signal.
            started_at (datetime): When THIS worker process registered.
            max_jobs (int | None): The worker's configured parallel-job capacity (arq concurrency);
                None when an older-build worker does not report it.
            cpu_percent (float | None): The worker process's recent CPU utilisation percent (may exceed
                100 on a multi-core host); None when not sampled (older build or a psutil error).
            mem_mb (float | None): The worker process's resident memory in megabytes; None when not sampled.
            mem_percent (float | None): The worker process's resident memory as a percent of host RAM;
                None when not sampled.
        """
        statement = pg_insert(WorkerHeartbeat).values(
            worker_id=worker_id,
            worker_name=worker_name,
            last_seen=last_seen,
            started_at=started_at,
            max_jobs=max_jobs,
            cpu_percent=cpu_percent,
            mem_mb=mem_mb,
            mem_percent=mem_percent,
        )
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[WorkerHeartbeat.worker_id],
                set_={
                    "worker_name": worker_name,
                    "last_seen": last_seen,
                    "started_at": started_at,
                    "max_jobs": max_jobs,
                    "cpu_percent": cpu_percent,
                    "mem_mb": mem_mb,
                    "mem_percent": mem_percent,
                },
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
    async def list_heartbeats(session: AsyncSession) -> list[WorkerHeartbeat]:
        """Return every worker heartbeat row, ordered by worker id — the fleet liveness snapshot."""
        result = await session.execute(
            select(WorkerHeartbeat).order_by(WorkerHeartbeat.worker_id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_running_for_worker(session: AsyncSession, worker_id: str) -> list[Job]:
        """
        Return the RUNNING jobs stamped with EXACTLY this worker id — its own leftovers only.

        Called at that worker's STARTUP: the process has no in-flight tasks yet, so any RUNNING row
        still carrying its ``worker_id`` is a leftover from its previous incarnation that never marked
        the row terminal. The ``worker_id == worker_id`` filter is deliberately exact: it matches ONLY
        the caller's own rows, never a sibling replica's live jobs.

        Because ``worker_id`` is the container hostname (stable only within a container's lifetime),
        this covers a SAME-CONTAINER restart (a dev hot-reload / in-place respawn) — where the id is
        preserved — but NOT a crash/recreate that mints a new hostname: those orphans carry the OLD
        id and this returns nothing, leaving them to the heartbeat reaper (``list_stale``). See
        ``JobsFacade.reclaim_worker_jobs`` for the full contract.

        Args:
            session (AsyncSession): The active DB session.
            worker_id (str): The (per-container-lifetime) hostname of the worker reclaiming its own
                orphans.

        Returns:
            list[Job]: This worker id's leftover RUNNING jobs (empty after a container recreate).
        """
        result = await session.execute(
            select(Job).where(Job.status == JobStatus.RUNNING, Job.worker_id == worker_id)
        )
        return list(result.scalars().all())


__all__ = ["WorkerHeartbeatApi"]
