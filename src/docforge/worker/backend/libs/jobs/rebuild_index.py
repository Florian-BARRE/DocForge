# ====== Code Summary ======
# The rebuild_collection_index arq task — recreates a collection's Qdrant store from its CURRENT schema
# without re-embedding any chunk content, so fields made semantic/lexical after first ingest get their
# named vectors (Qdrant cannot add one to a live collection) and metadata BM25 vectors get the IDF
# modifier. Order: wait for the collection's other live jobs (bounded) → copy into a fresh store and
# swap it under the stable name (StoreRebuildFacade) → backfill filter payloads + metadata vectors from
# Postgres (the dense metadata values ARE re-embedded through the collection's embed provider — small,
# but a provider call) → reconcile (enabled overrides, documents deleted mid-copy, needs_reindex).
# Drives the PRE-CREATED rebuild_index job row (document_id NULL) through its lifecycle. The task
# re-reads its own row while waiting and between copy batches: a cooperative cancel (or a reap that
# turned the row terminal) aborts BEFORE the swap — the temp is dropped, the old store stays live —
# and the row ends CANCELLED. Once the swap happened, the rebuild finishes (the new store is live).

# ====== Standard Library Imports ======
import uuid
from datetime import UTC, datetime
from typing import Any

# ====== Internal Project Imports (worker) ======
from backend.context import CONTEXT
from shared_libs.services.db.facades import AbortProbe, RebuildCancelledError
from shared_libs.services.db.postgresql.tables import JobStatus


def _abort_probe(job_uuid: uuid.UUID) -> AbortProbe:
    """The own-row check: stop once the row is gone, terminal, or asked to cancel."""

    async def _should_abort() -> bool:
        job = await CONTEXT.database.jobs.get(job_uuid)
        return job is None or job.status in JobStatus.terminal() or bool(job.cancel_requested)

    return _should_abort


async def _run(collection_uuid: uuid.UUID, job_uuid: uuid.UUID) -> dict[str, Any]:
    """Run the rebuild steps in order and return the summary (raises on any failure)."""
    database = CONTEXT.database
    should_abort = _abort_probe(job_uuid)
    # 1. Never copy a moving store: wait for the jobs that were live when this one started.
    await database.index_rebuild.wait_for_idle(
        collection_uuid,
        job_uuid,
        CONTEXT.RUNTIME_CONFIG.WORKER_REBUILD_INDEX_WAIT_SECONDS,
        should_abort=should_abort,
    )
    # 2. Copy into a schema-derived store and swap it in (drops the temp on a pre-swap failure or
    #    cancel — the own-row probe runs between batches and right before the swap).
    await database.jobs.set_progress(job_uuid, "copy", 10)
    copy = await database.store_rebuild.rebuild(
        collection_uuid,
        CONTEXT.RUNTIME_CONFIG.WORKER_REBUILD_INDEX_BATCH_SIZE,
        should_abort=should_abort,
    )
    # 3. Refill the denormalised metadata from Postgres (meta BM25 vectors were dropped on copy).
    await database.jobs.set_progress(job_uuid, "backfill", 70)
    await database.filters.backfill_collection_filter_payloads(collection_uuid)
    await database.meta_vectors.backfill_collection_meta_vectors(collection_uuid)
    # 4. Converge with Postgres and derive needs_reindex honestly.
    await database.jobs.set_progress(job_uuid, "reconcile", 90)
    reconciled = await database.index_rebuild.reconcile(collection_uuid, copy)
    # A cooperative cancel that landed after the last pre-swap probe came too late to stop the
    # swap: the rebuild completed, so say so rather than silently ignore the request.
    if await should_abort():
        CONTEXT.logger.warning(
            f"Rebuild {job_uuid}: cancel requested after the swap — too late, the rebuild completed"
        )
    return {
        "physical": copy.physical,
        "copied_points": copy.copied_points,
        "first_rebuild": copy.first_rebuild,
        "missing_vectors": reconciled.missing_vectors,
        "reingest_required_fields": reconciled.reingest_required_fields,
        "needs_reindex": reconciled.needs_reindex,
    }


async def _cancelled(job_uuid: uuid.UUID, job_id: str, reason: str) -> dict[str, Any]:
    """End a pre-swap abort: CANCELLED (a no-op when a reaper/force already closed the row)."""
    await CONTEXT.database.jobs.force_terminate(job_uuid, reason=f"cancelled: {reason}")
    CONTEXT.logger.info(f"Rebuild job {job_id} aborted before the swap: {reason}")
    return {"cancelled": True}


async def rebuild_collection_index(
    ctx: dict[str, Any], collection_id: str, job_id: str
) -> dict[str, Any]:
    """
    Rebuild a collection's Qdrant store from its current schema (no content re-embed).

    Args:
        ctx (dict): arq's context dict (``job_try`` is the attempt counter).
        collection_id (str): The collection to rebuild (UUID as string).
        job_id (str): The pre-created rebuild_index job row to drive (UUID as string).

    Returns:
        dict[str, Any]: The new physical store, copied points, swap mode, residual missing vectors
            (``{"skipped": True}`` when the row was already terminal at dequeue).
    """
    database = CONTEXT.database
    collection_uuid, job_uuid = uuid.UUID(collection_id), uuid.UUID(job_id)
    # 0. Dequeue-skip: a terminal row (cancelled while queued, or a zombie re-delivery the reaper already
    #    failed) no longer holds the admission lock — ingests may be live, so copying now is unsafe.
    #    A vanished row (the collection was deleted while queued) is skipped too.
    existing = await database.jobs.get(job_uuid)
    if existing is None or existing.status in JobStatus.terminal():
        state = existing.status.value if existing is not None else "deleted"
        CONTEXT.logger.info(f"Skipping rebuild job {job_id} (status={state}) at dequeue")
        return {"skipped": True}
    # 1. Claim the job.
    await database.jobs.mark_running(
        job_uuid,
        worker_id=CONTEXT.worker_id,
        attempt=ctx.get("job_try") or 1,
        started_at=datetime.now(UTC),
    )
    try:
        # 2. The rebuild proper.
        summary = await _run(collection_uuid, job_uuid)
    except RebuildCancelledError as exc:
        # 3a. Own-row stop before the swap: the temp is already dropped, the old store untouched.
        return await _cancelled(job_uuid, job_id, str(exc))
    except Exception as exc:
        # 3b. Fail the job with the cause; a pre-swap failure left the old store live and untouched.
        await database.jobs.mark_failed(
            job_uuid, error=str(exc), finished_at=datetime.now(UTC), error_type=type(exc).__name__
        )
        raise
    # 4. Vectors still missing after the rebuild = the schema changed meanwhile: say so, loudly.
    if summary["missing_vectors"]:
        await database.jobs.mark_failed(
            job_uuid,
            error=(
                f"index rebuilt, but vectors {summary['missing_vectors']} are still missing "
                f"(the schema changed during the rebuild) — run rebuild_index again"
            ),
            finished_at=datetime.now(UTC),
            error_type="rebuild_incomplete",
        )
        return summary
    # 5. Chunk-scope vectors a rebuild cannot fill: DONE, but needs_reindex stays raised — say why.
    if summary["reingest_required_fields"]:
        CONTEXT.logger.warning(
            f"Rebuild {job_id}: reingest required for chunk-scope field(s) "
            f"{summary['reingest_required_fields']} (a rebuild cannot fill their vectors)"
        )
    await database.jobs.mark_done(job_uuid, finished_at=datetime.now(UTC))
    CONTEXT.logger.info(f"Rebuilt index of collection {collection_id} (job {job_id}): {summary}")
    return summary


__all__ = ["rebuild_collection_index"]
