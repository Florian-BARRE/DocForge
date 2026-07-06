# ====== Code Summary ======
# The ingest_document arq task — the worker's whole job, in pipeline order: mark the job running,
# rehydrate the inputs (document row + original bytes from S3 + the collection's contract and
# pipeline blob), run the pipeline (fresh input, live progress), translate the delivery, persist
# through the facade (S3 → Postgres one-tx → Qdrant), close the job. Any failure marks BOTH the
# document and the job failed with the error in clear, then re-raises so arq accounts the attempt.

# ====== Standard Library Imports ======
import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

# ====== Local Project Imports ======
from persistence import RunTranslator

# ====== Internal Project Imports (worker) ======
from backend.context import CONTEXT

# ====== Internal Project Imports ======
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.public_models import CollectionContract, MetadataFieldSpec, SourceDocument
from shared_libs.services.db.postgresql.tables import MetadataField
from shared_libs.services.db.s3 import S3ObjectApi

# ====== Local Project Imports ======
from .progress import JobProgressRecorder


def _contract_from_rows(collection: Any, schema: list[MetadataField]) -> CollectionContract:
    """Build the pipeline's run-input contract from the collection + field rows."""
    return CollectionContract(
        collection_id=collection.id,
        name=collection.name,
        supported_formats=list(collection.supported_formats),
        max_file_size_bytes=collection.max_file_size_bytes,
        fields=[
            MetadataFieldSpec(
                field_name=row.field_name,
                field_type=row.field_type,
                required=row.required,
                filterable=row.filterable,
                lexical=row.lexical,
                semantic=row.semantic,
                origin=row.origin,
                scope=row.scope,
            )
            for row in schema
        ],
    )


async def ingest_document(ctx: dict[str, Any], document_id: str, job_id: str) -> None:
    """
    Execute one ingestion end to end: rehydrate → run → translate → persist.

    Args:
        ctx (dict): arq's context dict (unused — services live on CONTEXT).
        document_id (str): The admitted document's UUID (the queue carries ids only).
        job_id (str): The job row driving the lifecycle/status.
    """
    database, s3, runner = CONTEXT.database, CONTEXT.s3, CONTEXT.runner
    doc_uuid, job_uuid = uuid.UUID(document_id), uuid.UUID(job_id)

    # arq's job_try is the attempt counter (1 on first run, increments on retries).
    await database.jobs.mark_running(
        job_uuid,
        worker_id=CONTEXT.worker_id,
        attempt=ctx.get("job_try") or 1,
        started_at=datetime.now(UTC),
    )
    try:
        # 1. Rehydrate the inputs: rows, original bytes (key = source_hash), contract + blob.
        document = await database.documents.get(doc_uuid)
        if document is None:
            raise RuntimeError(f"document {document_id} not found")
        collection = await database.collections.get(document.collection_id)
        schema = await database.collections.get_schema(document.collection_id)
        async with s3.client() as client:
            raw = await S3ObjectApi.get(client, s3.bucket, document.source_hash)
        field_names = {row.id: row.field_name for row in schema}
        declared = {
            field_names[meta.field_id]: meta.value
            for meta in await database.documents.get_metadata(doc_uuid)
            if meta.origin.value == "user" and meta.field_id in field_names
        }
        source = SourceDocument(filename=document.filename, content=raw, declared_meta=declared)
        contract = _contract_from_rows(collection, schema)
        blob = collection.pipeline or IngestPipeline.default_blob().model_dump(mode="json")

        # 2. Live progress: the recorder keeps the job row current (START = stage running
        #    now, END = percentage + one trace row) — root nodes only.
        root_ids = (
            [node.get("id", "") for node in blob.get("nodes", [])]
            if isinstance(blob, dict)
            else [node.id for node in blob.nodes]
        )
        on_progress = JobProgressRecorder(job_uuid, root_ids)

        # 3. Run (fresh input inside), then translate the delivery.
        bundle, _record = await runner.run(
            blob, source, contract,
            timeout_seconds=CONTEXT.job_timeout_seconds,
            progress_callback=on_progress,
        )
        strategy = next(
            (node.get("kind", "") for node in blob.get("nodes", [])
             if isinstance(node, dict) and node.get("family") == "chunker"),
            "unknown",
        )
        config_hash = hashlib.sha256(
            json.dumps(blob, sort_keys=True, default=str).encode()
        ).hexdigest()
        translated = RunTranslator.translate(doc_uuid, bundle, schema, strategy, config_hash)

        # 4. Persist in the safe order: blobs (S3) → the one-tx save (PG) → the vectors (Qdrant).
        await database.ingestion.store_blobs(translated.objects, translated.blob_rows)
        await database.ingestion.save(doc_uuid, translated.payload)
        if translated.points:
            await database.ingestion.index(
                document.collection_id, translated.dense_dim, translated.points
            )
        await database.jobs.mark_done(job_uuid, finished_at=datetime.now(UTC))

    except Exception as exc:
        # Both truths flagged, the error in clear; re-raise so arq accounts the attempt.
        CONTEXT.logger.exception(f"Ingestion failed for document {document_id}: {exc}")
        await database.ingestion.mark_failed(doc_uuid)
        await database.jobs.mark_failed(
            job_uuid, error=f"{type(exc).__name__}: {exc}", finished_at=datetime.now(UTC)
        )
        raise


__all__ = ["ingest_document"]
