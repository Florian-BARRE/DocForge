# ====== Code Summary ======
# gc_artifact_cache — the arq cron that bounds the stage-artifact cache. The cache never deletes on
# its own: a stored parse IR (S3 bytes + pointer row) would accumulate forever across reingests and
# collections. When WORKER_ARTIFACT_GC_ENABLED this cron evicts rows by TTL (LRU on last_hit_at) and
# a per-collection byte cap, then reclaims any S3 stage-artifact blob whose LAST pointer was removed
# (the ref-count orphan sweep). Idempotent: an already-evicted row/blob no longer matches, so a
# re-run or a second worker is a harmless no-op.

# ====== Standard Library Imports ======
from datetime import UTC, datetime, timedelta
from typing import Any

# ====== Internal Project Imports (worker) ======
from backend.context import CONTEXT


async def gc_artifact_cache(ctx: dict[str, Any]) -> int:
    """
    Evict stale/over-cap cached artefacts (TTL + per-collection LRU) and sweep freed S3 blobs.

    Args:
        ctx (dict): arq's context dict (unused — services live on CONTEXT).

    Returns:
        int: The number of cache pointer rows evicted (0 when disabled or nothing was stale).
    """
    config = CONTEXT.RUNTIME_CONFIG
    # Belt-and-suspenders: the cron is not registered when GC is off (see app.py), but a direct or
    # scheduled call must still be a no-op rather than pruning behind the flag.
    if not config.WORKER_ARTIFACT_GC_ENABLED:
        return 0
    summary = await CONTEXT.database.artifact_cache.prune(
        datetime.now(UTC),
        timedelta(days=config.CACHE_TTL_DAYS),
        config.CACHE_MAX_BYTES_PER_COLLECTION,
        blob_grace=timedelta(minutes=config.CACHE_BLOB_GRACE_MINUTES),
    )
    if summary.evicted_rows or summary.freed_blobs:
        CONTEXT.logger.info(
            f"Artifact-cache GC evicted {summary.evicted_rows} row(s), "
            f"freed {summary.freed_blobs} blob(s)"
        )
    return summary.evicted_rows


__all__ = ["gc_artifact_cache"]
