# ====== Code Summary ======
# gc_trace_payloads — the arq cron that enforces full execution-trace retention. The full-capture tier
# stores each node's raw input/output payload in the object store under a job-prefixed key; nothing
# deletes them on its own, so they accumulate forever. When WORKER_TRACE_RETENTION_DAYS > 0 this cron
# reclaims the ``trace/{job_id}/`` space of jobs older than that window (and clears their DB refs, so
# the pass converges) via the TracePayloadFacade. Guarded by a positive retention window — at 0
# (keep-forever) the cron is not even registered (see app.py). Idempotent: a purged job no longer
# matches, so a re-run or a second worker is a harmless no-op.

# ====== Standard Library Imports ======
from datetime import UTC, datetime, timedelta
from typing import Any

# ====== Internal Project Imports (worker) ======
from backend.context import CONTEXT


async def gc_trace_payloads(ctx: dict[str, Any]) -> int:
    """
    Purge the stored full-trace payloads of jobs older than the configured retention window.

    Args:
        ctx (dict): arq's context dict (unused — services live on CONTEXT).

    Returns:
        int: The number of jobs whose payloads were purged (0 when disabled or nothing was old enough).
    """
    config = CONTEXT.RUNTIME_CONFIG
    # Belt-and-suspenders: the cron is not registered at retention 0 (see app.py), but a direct or
    # scheduled call must still be a no-op rather than purging behind the keep-forever setting.
    if config.WORKER_TRACE_RETENTION_DAYS <= 0:
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=config.WORKER_TRACE_RETENTION_DAYS)
    purged = await CONTEXT.database.trace_payloads.gc_before(
        cutoff, config.WORKER_TRACE_GC_BATCH_SIZE
    )
    if purged:
        CONTEXT.logger.info(
            f"Trace retention purged {purged} job(s)' payloads older than "
            f"{config.WORKER_TRACE_RETENTION_DAYS}d (cutoff {cutoff.isoformat()})"
        )
    return purged


__all__ = ["gc_trace_payloads"]
