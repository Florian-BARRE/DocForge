# ====== Code Summary ======
# gc_audit_log — the arq cron that enforces audit-log retention. The audit trail is append-only and
# grows unbounded; when AUDIT_RETENTION_DAYS > 0 this cron deletes every row older than that window
# via the AuditFacade. Guarded by WORKER_AUDIT_GC_ENABLED AND by a positive retention window (with
# retention at 0 = keep-forever the cron is not even registered — see app.py). Idempotent: a pruned
# row no longer matches, so a re-run or a second worker is a harmless no-op.

# ====== Standard Library Imports ======
from datetime import UTC, datetime, timedelta
from typing import Any

# ====== Internal Project Imports (worker) ======
from backend.context import CONTEXT


async def gc_audit_log(ctx: dict[str, Any]) -> int:
    """
    Delete every audit row older than the configured retention window.

    Args:
        ctx (dict): arq's context dict (unused — services live on CONTEXT).

    Returns:
        int: The number of rows pruned (0 when disabled or nothing was old enough).
    """
    config = CONTEXT.RUNTIME_CONFIG
    # Belt-and-suspenders: the cron is not registered when GC is off or retention is keep-forever
    # (see app.py), but a direct/scheduled call must still be a no-op rather than pruning behind it.
    if not config.WORKER_AUDIT_GC_ENABLED or config.AUDIT_RETENTION_DAYS <= 0:
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=config.AUDIT_RETENTION_DAYS)
    pruned = await CONTEXT.database.audit.prune(cutoff)
    if pruned:
        CONTEXT.logger.info(
            f"Audit retention pruned {pruned} row(s) older than "
            f"{config.AUDIT_RETENTION_DAYS}d (cutoff {cutoff.isoformat()})"
        )
    return pruned


__all__ = ["gc_audit_log"]
