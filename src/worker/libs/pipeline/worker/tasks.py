# ====== Code Summary ======
# arq task definitions for the DocForge P2/P3 pipeline.
# Each task function is registered in WorkerSettings.functions and enqueued by the API.
# Tasks download their inputs from S3 and update job/document status in Postgres.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from datetime import UTC, datetime

# ====== Third-Party Library Imports ======
from arq.worker import Retry
from loggerplusplus import loggerplusplus

from common_libs.config.pipeline import PipelineConfig
from common_libs.observability.events import EventPublisher

# ====== Internal Project Imports ======
from libs.pipeline.engine import StageEngine
from common_libs.storage.postgres.client import PostgresClient
from common_libs.storage.postgres.repositories import (
    CollectionRepository,
    DocumentRepository,
    JobRepository,
)

_logger = loggerplusplus.bind(identifier="WORKER_TASK")

# Must match WorkerSettings.max_tries — controls when we give up vs. schedule a retry.
_MAX_TRIES: int = 3


async def run_pipeline_task(
    ctx: dict,
    document_id: str,
    source_hash: str,
    filename: str,
    pipeline_version: str,
    job_id: str,
    collection_id: str | None = None,
) -> dict:
    """
    arq task: run the full pipeline (S0 → S1 → S2 → S4 → S5 → S6) for a single document.

    Lifecycle:
    1. Transition job status → running.
    2. Download the original file from S3 (uploaded at admission by the API).
    3. Delegate to StageEngine.run() — fingerprint, cache check, stage execution, persist.
    4. Transition job status → done (or failed on error, then re-raise so arq retries).

    The task receives ``document_id`` and ``source_hash`` rather than raw bytes to keep
    the Redis payload small.  The file was uploaded to S3 by the ingest endpoint before
    enqueuing this job.

    Args:
        ctx (dict): arq worker context — contains ``engine``, ``postgres``, ``job_repo``.
        document_id (str): Document UUID string.
        source_hash (str): SHA-256 hex of the original file (S3 content-address key).
        filename (str): Original filename (needed for format detection inside S0).
        pipeline_version (str): Collection pipeline version tag.
        job_id (str): Job UUID string (created at admission by the API).
        collection_id (str | None): Qdrant collection name for S6 indexing.  None = no indexing.

    Returns:
        dict: Summary of the completed run (document_id, job_id, stage fingerprints).
    """
    engine: StageEngine = ctx["engine"]
    postgres: PostgresClient = ctx["postgres"]
    job_repo: JobRepository = ctx["job_repo"]
    collection_repo: CollectionRepository = ctx["collection_repo"]
    document_repo: DocumentRepository = ctx["document_repo"]

    # Observability context (Brique A): worker identity, event bus, retry attempt.
    event_publisher: EventPublisher = ctx["event_publisher"]
    worker_id: str = ctx["worker_id"]
    job_try: int = ctx.get("job_try", 1)

    doc_uuid = uuid.UUID(document_id)
    job_uuid = uuid.UUID(job_id)

    _logger.info(
        f"Task started: document_id={document_id} job_id={job_id} "
        f"worker={worker_id} attempt={job_try} source_hash={source_hash[:8]}…"
    )

    # 1. Transition job → running, recording worker attribution + start time, and surface it.
    #    ctx["current_job_id"] feeds the worker heartbeat so the dashboard shows the active job.
    ctx["current_job_id"] = job_id
    async with postgres.session() as session:
        await job_repo.mark_running(
            session, job_uuid,
            worker_id=worker_id, attempt=job_try, started_at=datetime.now(UTC),
        )
    await event_publisher.job_updated({
        "id": job_id, "document_id": document_id, "collection_id": collection_id,
        "status": "running", "worker_id": worker_id, "attempt": job_try, "progress": 0,
    })

    # Coarse progress hook: each stage boundary updates the job row + publishes a live event.
    async def _progress_cb(stage: str, percent: int) -> None:
        async with postgres.session() as session:
            await job_repo.update_progress(session, job_uuid, stage, percent)
        # Carry collection_id/document_id so the SSE collection stream can scope this progress.
        await event_publisher.stage_progress(
            job_id, stage, percent, collection_id=collection_id, document_id=document_id,
        )

    # 2. Load the frozen collection contract (spec §3): pipeline config + metadata schema.
    # This makes full ingestion run the exact stack the playground previewed, and materialize
    # the per-field named vectors the metadata schema declares (spec §7.2).
    pipeline_config: PipelineConfig | None = None
    metadata_fields: list[dict] | None = None
    doc_user_meta: dict | None = None
    if collection_id is not None:
        async with postgres.session() as session:
            collection = await collection_repo.get_by_id(session, uuid.UUID(collection_id))
            if collection is not None:
                pipeline_config = PipelineConfig.from_dict(collection.pipeline)
                # Snapshot metadata fields as plain dicts (decoupled from the ORM session).
                metadata_fields = [
                    {
                        "field_name": f.field_name, "field_type": f.field_type,
                        "filterable": f.filterable, "lexical": f.lexical, "semantic": f.semantic,
                    }
                    for f in collection.metadata_fields
                ]
            # User-provided business metadata for this document (values for custom fields)
            doc = await document_repo.get_by_id(session, doc_uuid)
            if doc is not None and doc.user_meta:
                doc_user_meta = dict(doc.user_meta)

    # 3. Run the stage engine — it downloads the original from S3 internally
    try:
        result = await engine.run(
            doc_id=doc_uuid,
            source_hash=source_hash,
            filename=filename,
            pipeline_version=pipeline_version,
            file_bytes=None,   # engine downloads from S3: originals/{source_hash}
            dry_run=False,
            collection_id=collection_id,
            pipeline_config=pipeline_config,
            metadata_fields=metadata_fields,
            doc_user_meta=doc_user_meta,
            progress_cb=_progress_cb,
        )

        # 4. Transition job → done (records finish time; progress reads back as 100).
        # This is job STATE, not pure telemetry: it is intentionally NOT wrapped — if persisting
        # the terminal state fails, the job must fail (and arq retry) rather than silently report
        # success. Only the event publish below is best-effort (EventPublisher swallows internally).
        async with postgres.session() as session:
            await job_repo.mark_finished(
                session, job_uuid, "done", finished_at=datetime.now(UTC),
            )
        ctx["current_job_id"] = None
        ctx["jobs_processed"] = int(ctx.get("jobs_processed", 0)) + 1
        await event_publisher.job_updated({
            "id": job_id, "document_id": document_id, "collection_id": collection_id,
            "status": "done", "worker_id": worker_id, "attempt": job_try, "progress": 100,
        })

        _logger.info(
            f"Task done: document_id={document_id} job_id={job_id} "
            f"fps={result.stage_fingerprints}"
        )
        return {
            "document_id": document_id,
            "job_id": job_id,
            "stage_fingerprints": result.stage_fingerprints,
            "from_cache": result.from_cache,
            "budget_spent": result.budget_spent,
            "n_chunks": (
                result.s4_result.n_text_chunks
                + result.s4_result.n_figure_chunks
                + result.s4_result.n_table_chunks
                + result.s4_result.n_parent_chunks
            ) if result.s4_result is not None else 0,
            "n_indexed": result.s6_result.n_upserted_qdrant if result.s6_result is not None else 0,
        }

    except Exception as exc:
        # 5. Mark job as failed in the DB on every attempt; release the worker's active-job slot
        error_msg = f"{type(exc).__name__}: {exc}"
        _logger.error(
            f"Task failed (attempt {job_try}/{_MAX_TRIES}): "
            f"document_id={document_id} job_id={job_id} {error_msg}"
        )
        async with postgres.session() as session:
            await job_repo.mark_finished(
                session, job_uuid, "failed",
                finished_at=datetime.now(UTC), error=error_msg,
            )
        ctx["current_job_id"] = None
        await event_publisher.job_updated({
            "id": job_id, "document_id": document_id, "collection_id": collection_id,
            "status": "failed", "worker_id": worker_id, "attempt": job_try, "error": error_msg,
        })

        # 6. Permanent failure on the last attempt — let arq record the final error
        if job_try >= _MAX_TRIES:
            ctx["jobs_processed"] = int(ctx.get("jobs_processed", 0)) + 1
            raise

        # 7. Non-final attempt: schedule exponential back-off retry (30s, 60s, …)
        defer_s = 30 * (2 ** (job_try - 1))
        _logger.info(f"Task retry scheduled in {defer_s}s: document_id={document_id}")
        raise Retry(defer=defer_s)
