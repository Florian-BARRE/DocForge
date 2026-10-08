# ====== Code Summary ======
# The sync_document_metadata arq task — the lightweight per-document re-embed that follows a metadata
# VALUE edit (PATCH /documents/{id}/metadata). It re-embeds ONLY the document's short metadata VALUES
# into their named vectors (semantic dense / lexical sparse) on every one of its chunk points, via
# the MetaVectorSyncFacade — never the chunk CONTENT. The filterable payload repaint already ran
# synchronously in the request; this task re-runs it too (idempotent) so a single entry point fully
# reconciles the document's denormalised metadata. Enqueued only when a changed field is
# semantic/lexical; idempotent, safe to re-run.

# ====== Standard Library Imports ======
import uuid
from datetime import UTC, datetime
from typing import Any

# ====== Internal Project Imports (worker) ======
from backend.context import CONTEXT
from shared_libs.pipelines.build.validation_message import ValidationMessage


async def sync_document_metadata(
    ctx: dict[str, Any], document_id: str, job_id: str
) -> dict[str, int]:
    """
    Re-embed a single document's metadata values after a value edit (no content re-embed).

    Drives the PRE-CREATED tracked ``metadata_sync`` job row through its lifecycle (the same
    "caller mints the row, worker transitions it" contract as ingestion) so the UI can watch it
    complete: RUNNING at start, DONE on success (progress=100), FAILED with the error on exception.
    The job tracks no pipeline stages/trace — that is expected for a side-job; no stage events are
    fabricated. Idempotent and safe to re-run (the sync facades no-op when the document has no points).

    Args:
        ctx (dict): arq's context dict (``job_try`` is the attempt counter; services live on CONTEXT).
        document_id (str): The document to re-sync (UUID as string; the queue carries strings).
        job_id (str): The tracked job row's id to drive (UUID as string).

    Returns:
        dict[str, int]: ``{"meta_points": n, "filter_points": m}`` — points patched per axis.
    """
    database = CONTEXT.database
    document_uuid = uuid.UUID(document_id)
    job_uuid = uuid.UUID(job_id)

    # 1. Claim the tracked job (PENDING → RUNNING). mark_running is retry-safe and refuses to re-open
    #    a terminal row, so a zombie re-delivery can never resurrect a finished sync.
    await database.jobs.mark_running(
        job_uuid,
        worker_id=CONTEXT.worker_id,
        attempt=ctx.get("job_try") or 1,
        started_at=datetime.now(UTC),
    )
    try:
        # 2. Re-embed the short metadata VALUES into their named vectors on every chunk point.
        meta_points = await database.meta_vectors.sync_document_meta_vectors(document_uuid)
        # 3. Repaint the filterable payloads too (idempotent) so this one task fully reconciles the doc.
        filter_points = await database.filters.sync_document_filter_payloads(document_uuid)
        # 4. Complete the job (conditional on it still being RUNNING; sets progress=100).
        await database.jobs.mark_done(job_uuid, finished_at=datetime.now(UTC))
        CONTEXT.logger.info(
            f"Synced metadata for document {document_id} (job {job_id}): "
            f"{meta_points} meta point(s), {filter_points} filter point(s)"
        )
        return {"meta_points": meta_points, "filter_points": filter_points}
    except Exception as exc:
        # 5. Fail the tracked job with the error (mark_failed NUL-strips the text at the DB edge), then
        #    re-raise so arq accounts the attempt — mirrors the ingest worker's terminal contract.
        await database.jobs.mark_failed(
            job_uuid,
            error=ValidationMessage.describe(exc),
            finished_at=datetime.now(UTC),
            error_type=type(exc).__name__,
        )
        raise


__all__ = ["sync_document_metadata"]
