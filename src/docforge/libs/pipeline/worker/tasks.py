# ====== Code Summary ======
# arq task definitions for the DocForge P2/P3 pipeline.
# Each task function is registered in WorkerSettings.functions and enqueued by the API.
# Tasks download their inputs from S3 and update job/document status in Postgres.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

from libs.core.contracts.pipeline_config import PipelineConfig
from libs.data.storage.postgres.client import PostgresClient
from libs.data.storage.postgres.repositories import (
    CollectionRepository,
    DocumentRepository,
    JobRepository,
)

# ====== Internal Project Imports ======
from libs.engine.engine import StageEngine

_logger = loggerplusplus.bind(identifier="WORKER_TASK")


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

    doc_uuid = uuid.UUID(document_id)
    job_uuid = uuid.UUID(job_id)

    _logger.info(
        f"Task started: document_id={document_id} job_id={job_id} "
        f"source_hash={source_hash[:8]}…"
    )

    # 1. Transition job → running so the caller can observe progress immediately
    async with postgres.session() as session:
        await job_repo.update_status(session, job_uuid, "running")

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
        )

        # 4. Transition job → done
        async with postgres.session() as session:
            await job_repo.update_status(session, job_uuid, "done")

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
        # 5. Mark job as failed; arq will retry based on WorkerSettings.max_tries
        error_msg = f"{type(exc).__name__}: {exc}"
        _logger.error(f"Task failed: document_id={document_id} job_id={job_id} {error_msg}")
        async with postgres.session() as session:
            await job_repo.update_status(
                session, job_uuid, "failed", error=error_msg
            )
        raise
