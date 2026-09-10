# ====== Code Summary ======
# gc_job_history — the arq cron that enforces job-history retention. The observability tables (`job`
# and its cascading `job_stage_event` timeline) are append-only and grow unbounded; when
# JOB_HISTORY_RETENTION_DAYS > 0 this cron deletes every TERMINAL job older than that window via the
# JobsFacade (stage-events cascade with the row). Guarded by WORKER_JOB_HISTORY_GC_ENABLED AND by a
# positive retention window (with retention at 0 = keep-forever the cron is not even registered — see
# app.py). A job still carrying an un-GC'd full-trace payload is skipped by the query so this row
# prune never strands an object-store trace namespace (the separate trace GC reclaims those first).
# Idempotent: a pruned row no longer matches, so a re-run or a second worker is a harmless no-op.

# ====== Standard Library Imports ======
from datetime import UTC, datetime, timedelta
from typing import Any

# ====== Internal Project Imports (worker) ======
from backend.context import CONTEXT


async def gc_job_history(ctx: dict[str, Any]) -> int:
    """
    Delete every terminal job (and its stage-events) older than the configured retention window.

    Args:
        ctx (dict): arq's context dict (unused — services live on CONTEXT).

    Returns:
        int: The number of job rows pruned (0 when disabled or nothing was old enough).
    """
    config = CONTEXT.RUNTIME_CONFIG
    # Belt-and-suspenders: the cron is not registered when GC is off or retention is keep-forever
    # (see app.py), but a direct/scheduled call must still be a no-op rather than pruning behind it.
    if not config.WORKER_JOB_HISTORY_GC_ENABLED or config.JOB_HISTORY_RETENTION_DAYS <= 0:
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=config.JOB_HISTORY_RETENTION_DAYS)
    pruned = await CONTEXT.database.jobs.prune_history(cutoff)
    if pruned:
        CONTEXT.logger.info(
            f"Job-history retention pruned {pruned} terminal job(s) older than "
            f"{config.JOB_HISTORY_RETENTION_DAYS}d (cutoff {cutoff.isoformat()})"
        )
    return pruned


__all__ = ["gc_job_history"]
