# ====== Code Summary ======
# reap_stuck_jobs — the arq cron that clears orphaned ingestion jobs. When the dev worker hot-reloads
# (or crashes) mid-run, arq drops the in-flight task but the DB job row stays RUNNING forever and its
# document PROCESSING. Job.updated_at bumps on every progress write, so a wedged job's timestamp
# FREEZES; this cron fails every RUNNING job idle past the configured threshold (and releases its
# document to FAILED) via the JobsFacade. Guarded by WORKER_REAP_ENABLED; idempotent (a reaped row no
# longer matches RUNNING, so a re-run or a second worker is a harmless no-op).

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
    reaped: list[uuid.UUID] = await CONTEXT.database.jobs.reap_stale(
        config.WORKER_REAP_STALE_SECONDS
    )
    if reaped:
        minutes = config.WORKER_REAP_STALE_SECONDS // 60
        CONTEXT.logger.warning(
            f"Reaped {len(reaped)} stuck job(s) idle >{minutes}m "
            f"(presumed orphaned by a worker restart): {[str(job_id) for job_id in reaped]}"
        )
    return [str(job_id) for job_id in reaped]


__all__ = ["reap_stuck_jobs"]
