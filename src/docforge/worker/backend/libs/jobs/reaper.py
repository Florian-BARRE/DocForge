# ====== Code Summary ======
# reap_stuck_jobs — the arq cron that clears orphaned/wedged ingestion jobs. Two disjoint conditions:
# a DEAD-WORKER orphan (heartbeat stale/absent → worker_killed) recovered by reap_stale, and a
# LIVE-WORKER wedge (a job past its own job timeout while the worker keeps heartbeating →
# job_timeout_exceeded) recovered by reap_over_job_timeout — the job-level watchdog that closes the
# heartbeat veto's blind spot
# (an alive worker can hold a dead-wedged slot forever). Each fails the job FAILED with an attributed
# error_type + reason and releases its document to FAILED via the JobsFacade. It ALSO prunes crashed
# workers' stale heartbeats — a
# fleet-wide DELETE that used to run on every GET /jobs/workers/live and now belongs to this cron, so
# the read path is side-effect-free. Guarded by WORKER_REAP_ENABLED; idempotent (a reaped row no
# longer matches RUNNING, a pruned heartbeat is already gone — a re-run or a second worker is a no-op).

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Internal Project Imports (worker) ======
from backend.context import CONTEXT


async def reap_stuck_jobs(ctx: dict[str, Any]) -> list[str]:
    """
    Fail RUNNING jobs whose progress froze past the reap threshold (orphaned by a worker restart).

    Args:
        ctx (dict): arq's context dict (unused — services live on CONTEXT).

    Returns:
        list[str]: The reaped job ids (empty when reaping is disabled or nothing was stale).
    """
    config = CONTEXT.RUNTIME_CONFIG
    # Belt-and-suspenders: the cron is not even registered when reaping is disabled (see app.py),
    # but a direct/scheduled call must still be a no-op rather than reaping behind the flag.
    if not config.WORKER_REAP_ENABLED:
        return []
    # Two independent reap conditions, disjoint by worker-heartbeat freshness on the SAME cutoff
    # (WORKER_PRUNE_STALE_SECONDS), so a job lands in at most one:
    #
    # 1. DEAD-WORKER orphan (reap_stale → worker_killed): a job silent past WORKER_REAP_STALE_SECONDS
    #    whose worker heartbeat is stale/absent — the process is gone (crash / SIGKILL / OOM). A FRESH
    #    heartbeat vetoes this, so a long silent stage on a live worker is never reaped here.
    # 2. OVER-JOB-TIMEOUT wedge (reap_over_job_timeout → job_timeout_exceeded): a job on a LIVE worker
    #    (fresh heartbeat) whose total age blew past its per-collection effective job timeout + grace —
    #    a hung / runaway native stage arq's async cancel cannot kill. This is the job-LEVEL watchdog that
    #    closes the heartbeat veto's blind spot (an alive worker holding a dead-wedged slot forever).
    reaped: list[uuid.UUID] = await CONTEXT.database.jobs.reap_stale(
        config.WORKER_REAP_STALE_SECONDS, config.WORKER_PRUNE_STALE_SECONDS
    )
    if reaped:
        minutes = config.WORKER_REAP_STALE_SECONDS // 60
        CONTEXT.logger.warning(
            f"Reaped {len(reaped)} stuck job(s) idle >{minutes}m on a lost worker "
            f"(worker_killed): {[str(job_id) for job_id in reaped]}"
        )

    over_job_timeout: list[uuid.UUID] = await CONTEXT.database.jobs.reap_over_job_timeout(
        config.WORKER_JOB_TIMEOUT_SECONDS,
        config.WORKER_OVER_JOB_TIMEOUT_GRACE_SECONDS,
        config.WORKER_PRUNE_STALE_SECONDS,
    )
    if over_job_timeout:
        CONTEXT.logger.warning(
            f"Reaped {len(over_job_timeout)} over-job-timeout job(s) wedged on a live worker "
            f"(job_timeout_exceeded): {[str(job_id) for job_id in over_job_timeout]}"
        )
    reaped = reaped + over_job_timeout

    # Prune crashed workers' stale heartbeats here (moved off the GET /jobs/workers/live read path, so
    # a poll never triggers a fleet-wide DELETE). A cleanly-stopped worker already de-registered
    # itself; this clears the rest so the fleet view is not a graveyard.
    pruned = await CONTEXT.database.jobs.prune_stale_heartbeats(config.WORKER_PRUNE_STALE_SECONDS)
    if pruned:
        CONTEXT.logger.info(f"Pruned {len(pruned)} stale worker heartbeat(s): {pruned}")

    return [str(job_id) for job_id in reaped]


__all__ = ["reap_stuck_jobs"]
