# ====== Code Summary ======
# gc_idempotency_keys — the arq cron that enforces idempotency-store retention. The app stamps each
# idempotency record with an ``expires_at`` (now + IDEMPOTENCY_TTL_HOURS); nothing ever deletes an
# expired row, so the table would grow unbounded. When WORKER_IDEMPOTENCY_GC_ENABLED this cron deletes
# every row past its expiry via the IdempotencyFacade. Idempotent: a pruned row no longer matches, so
# a re-run or a second worker is a harmless no-op.

# ====== Standard Library Imports ======
from datetime import UTC, datetime
from typing import Any

# ====== Internal Project Imports (worker) ======
from backend.context import CONTEXT


async def gc_idempotency_keys(ctx: dict[str, Any]) -> int:
    """
    Delete every idempotency record whose ``expires_at`` is in the past.

    Args:
        ctx (dict): arq's context dict (unused — services live on CONTEXT).

    Returns:
        int: The number of records pruned (0 when disabled or nothing had expired).
    """
    config = CONTEXT.RUNTIME_CONFIG
    # Belt-and-suspenders: the cron is not registered when GC is off (see app.py), but a direct or
    # scheduled call must still be a no-op rather than pruning behind the flag.
    if not config.WORKER_IDEMPOTENCY_GC_ENABLED:
        return 0
    pruned = await CONTEXT.database.idempotency.prune(datetime.now(UTC))
    if pruned:
        CONTEXT.logger.info(f"Idempotency GC pruned {pruned} expired record(s)")
    return pruned


__all__ = ["gc_idempotency_keys"]
