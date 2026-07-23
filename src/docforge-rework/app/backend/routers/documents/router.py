# ====== Code Summary ======
# The documents router — the ADMISSION path (the backend's only write): receive the upload,
# content-address it, dedup, store the ORIGINAL blob (before enqueueing — the worker refetches
# by source_hash), admit document+job+declared metadata in one transaction, enqueue ids.
# The pipeline itself validates the content (formats, size, required fields) — the backend only
# checks what it needs structurally (collection exists, declared names exist in the schema).

# ====== Standard Library Imports ======
import hashlib
import json
import uuid

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldOrigin
from shared_libs.services.db.postgresql.tables import (
    Blob,
    BlobKind,
    Document,
    DocumentMetadata,
    DocumentStatus,
    Job,
    SourceKind,
)
from shared_libs.services.db.s3 import S3Object

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...utils.error_handling import auto_handle_errors
from ...utils.pipeline_validation import PipelineBlobValidator
from .models import DocumentEnabledResponse, EnabledPatch, UploadAccepted

router = APIRouter(prefix="/documents", tags=["documents"])


def _pipeline_version(pipeline_blob: dict) -> str:
    """Identity of the pipeline config — part of the dedup key (same doc, new config → re-run)."""
    return hashlib.sha256(
        json.dumps(pipeline_blob, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]


@router.post("", response_model=UploadAccepted, status_code=202)
@auto_handle_errors
async def upload_document(
    file: UploadFile = File(..., description="The document to ingest."),
    collection_id: uuid.UUID = Form(..., description="Target collection."),
    metadata: str = Form("{}", description="Declared metadata, JSON object {field: value}."),
) -> UploadAccepted:
    """
    Admit one document and enqueue its ingestion (asynchronous — poll the job for status).

    Returns:
        UploadAccepted: document + job ids (202), or the existing document when duplicate.
    """
    # 1. The collection must exist — everything else derives from it.
    collection = await CONTEXT.database.collections.get(collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")

    # 2. Fail-fast on a STALE contract, BEFORE any spend: a stored pipeline blob that no longer
    #    builds (e.g. it names a node kind the registry no longer knows) is a 422 here — nothing
    #    is read, stored, admitted or enqueued. Structural (no I/O), so cheap on every upload.
    PipelineBlobValidator.validate(collection.pipeline)

    # 3. Content-address the upload — the SAME identity the pipeline computes (sha256).
    content = await file.read()

    # 3b. Enforce the collection's size limit BEFORE storing — an oversized upload is a 422 here,
    #     never a blob written to S3 then rejected downstream.
    if len(content) > collection.max_file_size_bytes:
        raise HTTPException(
            status_code=422,
            detail=f"File exceeds the collection's limit "
                   f"({len(content)} > {collection.max_file_size_bytes} bytes).",
        )

    source_hash = hashlib.sha256(content).hexdigest()
    version = _pipeline_version(collection.pipeline)

    # 4. Dedup: same content + same pipeline config in this collection → nothing to re-run.
    existing = await CONTEXT.database.ingestion.find_duplicate(collection_id, source_hash, version)
    if existing is not None:
        return UploadAccepted(document_id=str(existing.id), job_id="", duplicate=True)

    # 5. Declared metadata: parse + resolve field names against the schema (structural check
    #    only — types/required are the pipeline admission node's job).
    try:
        declared: dict = json.loads(metadata)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"metadata is not valid JSON: {exc}")
    schema = await CONTEXT.database.collections.get_schema(collection_id)
    field_ids = {row.field_name: row.id for row in schema}
    unknown = sorted(set(declared) - set(field_ids))
    if unknown:
        raise HTTPException(
            status_code=422, detail=f"Unknown metadata field(s) for this collection: {unknown}"
        )

    # 6. Store the ORIGINAL bytes BEFORE enqueueing (key = source_hash — the worker refetches).
    filename = file.filename or "upload"
    mime = file.content_type or "application/octet-stream"
    await CONTEXT.database.ingestion.store_blobs(
        [S3Object(key=source_hash, data=content, content_type=mime)],
        [Blob(content_hash=source_hash, s3_key=source_hash, mime_type=mime,
              size_bytes=len(content), kind=BlobKind.ORIGINAL)],
    )

    # 7. Admission — document + job + declared metadata, ONE transaction.
    #    source_kind starts DIGITAL_BORN; the pipeline learns the real one (update_facts).
    document = Document(
        collection_id=collection_id,
        source_hash=source_hash,
        filename=filename,
        format=filename.rsplit(".", 1)[-1].lower() if "." in filename else "",
        mime_type=mime,
        file_size=len(content),
        source_kind=SourceKind.DIGITAL_BORN,
        status=DocumentStatus.PENDING,
        pipeline_version=version,
    )
    rows = [
        DocumentMetadata(field_id=field_ids[name], value=value, origin=FieldOrigin.USER)
        for name, value in declared.items()
    ]
    created, job = await CONTEXT.database.ingestion.admit(document, Job(), rows)

    # 8. Hand over to the worker — the queue message carries IDS ONLY.
    await CONTEXT.queue.enqueue_ingest(str(created.id), str(job.id))
    CONTEXT.logger.info(f"Admitted '{filename}' as {created.id} (job {job.id})")
    return UploadAccepted(document_id=str(created.id), job_id=str(job.id))


@router.patch("/{document_id}/enabled", response_model=DocumentEnabledResponse)
@auto_handle_errors
async def set_document_enabled(
    document_id: uuid.UUID, patch: EnabledPatch
) -> DocumentEnabledResponse:
    """
    Toggle a document's searchability (reversible, no re-ingest) — a single Postgres flag.

    Search excludes a disabled document's chunks via a bounded exclusion fed from this flag, so no
    Qdrant point is touched here (no per-chunk fan-out).

    Returns:
        DocumentEnabledResponse: The document id and its new state; 404 when the document is unknown.
    """
    # 1. The facade flips documents.enabled; False means the id never existed.
    existed = await CONTEXT.database.enablement.set_document_enabled(
        document_id, patch.enabled
    )
    if not existed:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found.")

    # 2. Echo the applied state.
    return DocumentEnabledResponse(document_id=str(document_id), enabled=patch.enabled)


__all__ = ["router"]
