# ====== Code Summary ======
# gc_expired_transfers — the arq cron that reclaims expired export bundles. An export stamps its
# tracking row with an ``expires_at`` and the download route refuses a bundle past it, but nothing
# ever DELETES the S3 object or the `collection_transfer` row — so both leak forever (unbounded
# storage + row growth). This cron sweeps every expired export bundle (S3 object + row) via the
# CollectionTransferFacade. Guarded by WORKER_TRANSFER_GC_ENABLED; idempotent (a reclaimed row no
# longer matches, so a re-run or a second worker is a harmless no-op).

# ====== Standard Library Imports ======
from datetime import UTC, datetime
from typing import Any

# ====== Internal Project Imports (worker) ======
from backend.context import CONTEXT


async def gc_expired_transfers(ctx: dict[str, Any]) -> list[str]:
    """
    Delete every expired export bundle (S3 object + tracking row) past its ``expires_at``.

    Args:
        ctx (dict): arq's context dict (unused — services live on CONTEXT).

    Returns:
        list[str]: The reclaimed transfer ids (empty when disabled or nothing had expired).
    """
    config = CONTEXT.RUNTIME_CONFIG
    # Belt-and-suspenders: the cron is not even registered when GC is disabled (see app.py), but a
    # direct/scheduled call must still be a no-op rather than reclaiming behind the flag.
    if not config.WORKER_TRANSFER_GC_ENABLED:
        return []
    reclaimed = await CONTEXT.database.transfer.gc_expired_bundles(datetime.now(UTC))
    if reclaimed:
        CONTEXT.logger.info(
            f"Transfer GC reclaimed {len(reclaimed)} expired export bundle(s): "
            f"{[str(transfer_id) for transfer_id in reclaimed]}"
        )
    return [str(transfer_id) for transfer_id in reclaimed]


__all__ = ["gc_expired_transfers"]
