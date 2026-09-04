# ====== Code Summary ======
# reap_stuck_transfers — the arq cron that clears orphaned collection transfers. A worker hard-killed
# (SIGKILL) or arq-timed-out mid export/import never runs the transfer task's ``except``, so its
# `collection_transfer` row stays RUNNING forever: the transfer GC never reclaims its staged bundle
# (GC sweeps only terminal, expired rows) and the UI shows an eternal spinner. The ingestion-job
# reaper does NOT cover this row (that one is document-scoped). This sibling sweep marks every RUNNING
# transfer whose ``updated_at`` froze past WORKER_TRANSFER_REAP_STALE_SECONDS as FAILED (via the
# TransferTrackerFacade), making it terminal + GC-reclaimable. Reuses WORKER_REAP_ENABLED as its
# master switch; idempotent (a reaped row no longer matches RUNNING, so a re-run/second worker is a
# no-op). See TransferTrackerFacade.reap_stale for the half-import residual it does NOT roll back.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports (worker) ======
from backend.context import CONTEXT


async def reap_stuck_transfers(ctx: dict[str, Any]) -> list[str]:
    """
    Fail RUNNING collection transfers stalled past the reap horizon (orphaned by a worker crash).

    Args:
        ctx (dict): arq's context dict (unused — services live on CONTEXT).

    Returns:
        list[str]: The reaped transfer ids (empty when reaping is disabled or nothing was stale).
    """
    config = CONTEXT.RUNTIME_CONFIG
    # Belt-and-suspenders: the cron is not even registered when reaping is disabled (see app.py),
    # but a direct/scheduled call must still be a no-op rather than reaping behind the flag.
    if not config.WORKER_REAP_ENABLED:
        return []
    reaped = await CONTEXT.database.transfer_tracker.reap_stale(
        config.WORKER_TRANSFER_REAP_STALE_SECONDS
    )
    if reaped:
        minutes = config.WORKER_TRANSFER_REAP_STALE_SECONDS // 60
        CONTEXT.logger.warning(
            f"Reaped {len(reaped)} stuck transfer(s) idle >{minutes}m "
            f"(presumed orphaned by a worker crash/hard-kill): "
            f"{[str(transfer_id) for transfer_id in reaped]}"
        )
    return [str(transfer_id) for transfer_id in reaped]


__all__ = ["reap_stuck_transfers"]
