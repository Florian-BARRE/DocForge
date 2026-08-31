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
from shared_libs.pipelines.ingest import (
    BlobNormalizationError,
    BlobNormalizer,
    IngestPipeline,
)
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
    # Flip the DOCUMENT row PENDING → PROCESSING too: mark_running only moves the JOB to RUNNING, so
    # without this the document reads "pending" for the whole run. Guarded to PENDING → PROCESSING,
    # and the terminal DONE/FAILED writes below still win.
    await database.ingestion.mark_processing(doc_uuid)
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

        # Normalize (auto-heal) the stored blob to the CURRENT engine topology before building the
        # graph: the expanded blob embeds engine-structural wiring that shifts when the engine
        # evolves, so a blob stored under an older engine is healed here rather than failing to
        # build. A blob that cannot be read back at all is a clear, collection-named error (recorded
        # on the job) — never a cryptic build crash after bytes are already stored.
        stored_blob = collection.pipeline or IngestPipeline.default_blob().model_dump(mode="json")
        try:
            blob = BlobNormalizer.normalize(stored_blob)
        except BlobNormalizationError as exc:
            raise RuntimeError(
                f"collection {collection.id} pipeline cannot be auto-migrated to the current "
                f"engine: {exc}"
            ) from exc

        # 2. Live progress: the recorder keeps the job row current (START = stage running
        #    now, END = percentage + one trace row) — root nodes only.
        root_ids = (
            [node.get("id", "") for node in blob.get("nodes", [])]
            if isinstance(blob, dict)
            else [node.id for node in blob.nodes]
        )
        on_progress = JobProgressRecorder(job_uuid, root_ids)

        # 3. Run (fresh input inside), then translate the delivery. The wall-clock budget is the
        #    collection's per-collection override when set, else the worker's global default (NULL).
        run_budget = collection.job_timeout_seconds or CONTEXT.job_timeout_seconds
        bundle, _record = await runner.run(
            blob,
            source,
            contract,
            timeout_seconds=run_budget,
            progress_callback=on_progress,
            preflight_enabled=CONTEXT.RUNTIME_CONFIG.WORKER_PREFLIGHT_ENABLED,
        )
        strategy = next(
            (
                node.get("kind", "")
                for node in blob.get("nodes", [])
                if isinstance(node, dict) and node.get("family") == "chunker"
            ),
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
                document.collection_id,
                doc_uuid,
                translated.dense_dim,
                translated.points,
            )
            # 5. Denormalise the document's filterable doc-scope metadata onto the fresh points
            #    (runs AFTER save() wrote generated doc metadata and index() minted the points),
            #    so a document-level field is searchable as a Qdrant filter without any re-embed.
            #    Best-effort: the document is already fully ingested and searchable here — a filter
            #    hiccup must NOT fail the job (which would re-embed on retry). The
            #    backfill_collection_filters job is the explicit repair path.
            try:
                await database.filters.sync_document_filter_payloads(doc_uuid)
            except Exception as filter_exc:
                CONTEXT.logger.warning(
                    f"Filter denormalisation failed for document {document_id} "
                    f"(ingestion kept; repair via backfill): {filter_exc}"
                )
            # 6. Populate the document-scope metadata named vectors (semantic dense / lexical sparse)
            #    on the same fresh points, so a metadata-only search resolves to a non-empty vector.
            #    Same best-effort contract as the filter sync: the document is already ingested and
            #    searchable — a meta-vector hiccup must NOT fail the job (retry would re-embed the
            #    content). The backfill_collection_meta_vectors job is the explicit repair path.
            try:
                await database.meta_vectors.sync_document_meta_vectors(doc_uuid)
            except Exception as meta_exc:
                CONTEXT.logger.warning(
                    f"Meta-vector population failed for document {document_id} "
                    f"(ingestion kept; repair via backfill): {meta_exc}"
                )
        await database.jobs.mark_done(job_uuid, finished_at=datetime.now(UTC))

    except Exception as exc:
        # Both truths flagged, the error in clear; re-raise so arq accounts the attempt. A run
        # failure carries a structured breadcrumb (deepest failing node + fan-out item) on the
        # exception; other failures (rehydrate/persist) fall back to the exception's own type.
        CONTEXT.logger.exception(f"Ingestion failed for document {document_id}: {exc}")
        breadcrumb = getattr(exc, "breadcrumb", None)
        await database.ingestion.mark_failed(doc_uuid)
        await database.jobs.mark_failed(
            job_uuid,
            error=f"{type(exc).__name__}: {exc}",
            finished_at=datetime.now(UTC),
            failed_node_id=breadcrumb.node_id if breadcrumb else None,
            failed_node_kind=breadcrumb.node_kind if breadcrumb else None,
            failed_item_index=breadcrumb.item_index if breadcrumb else None,
            error_type=breadcrumb.error_type if breadcrumb else type(exc).__name__,
        )
        raise


__all__ = ["ingest_document"]
