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
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile

# ====== Internal Project Imports ======
from shared_libs.pipelines.ingest import (
    BlobNormalizationError,
    BlobNormalizer,
    FormatProbeHelpers,
)
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
from ...libs.auth import AuthPrincipal, AuthzGuard, Capability, require
from ...utils.error_handling import auto_handle_errors
from ...utils.pipeline_validation import PipelineBlobValidator
from ...utils.upload_reader import UploadReader
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
    request: Request,
    file: UploadFile = File(..., description="The document to ingest."),
    collection_id: uuid.UUID = Form(..., description="Target collection."),
    metadata: str = Form("{}", description="Declared metadata, JSON object {field: value}."),
    principal: AuthPrincipal = Depends(require(Capability.WRITE)),
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

    # 2. Collection scope lives in the FORM BODY, so the path-param gate cannot see it — enforce it
    #    here: a key scoped to another collection is a 403 before anything is read or stored.
    AuthzGuard.assert_collection_scope(principal, str(collection_id))

    # 3. Fail-fast on a STALE contract, BEFORE any spend. First auto-heal the stored blob to the
    #    current engine (a blob stored under an older engine is normalized, not rejected — this is
    #    what removes the cryptic foreach_invalid_body that used to surface here), then structurally
    #    validate the healed shape. A blob that cannot be migrated at all is a clear 422 naming the
    #    collection and the one recovery — nothing is read, stored, admitted or enqueued.
    try:
        pipeline_blob = BlobNormalizer.normalize(collection.pipeline)
    except BlobNormalizationError as exc:
        raise HTTPException(status_code=422, detail=f"Collection {collection_id}: {exc}")
    PipelineBlobValidator.validate(pipeline_blob)

    # 4. OOM guard: refuse a grossly oversized body on its declared Content-Length before reading a
    #    single byte, THEN stream + content-address it in bounded windows (sha256 — the SAME
    #    identity the pipeline computes), aborting the instant it crosses the collection's ceiling.
    UploadReader.reject_oversized_body(request, collection.max_file_size_bytes)
    content, source_hash = await UploadReader.read_capped(file, collection.max_file_size_bytes)

    # 4b. Format gate — reject an unaccepted format HERE, before storing or enqueueing, so it fails
    #     in milliseconds at the boundary instead of ~minutes later inside the queued run's admit
    #     node. The detection is the SAME content sniff the admit node keys on (never the extension),
    #     so the two gates can never disagree. The admit-node check stays as defence in depth.
    detected_format, detected_mime = FormatProbeHelpers.detect(content, file.filename or "upload")
    if detected_format not in collection.supported_formats:
        raise HTTPException(
            status_code=422,
            detail=(
                f"detected format '{detected_format}' is not accepted for this collection "
                f"(allowed: {collection.supported_formats})"
            ),
        )

    # The dedup key hashes the HEALED blob — the exact topology the worker will run — so the version
    # is stable across engine evolutions of the same stage-level pipeline.
    version = _pipeline_version(pipeline_blob)

    # 5. Dedup: same content + same pipeline config in this collection → nothing to re-run.
    existing = await CONTEXT.database.ingestion.find_duplicate(collection_id, source_hash, version)
    if existing is not None:
        return UploadAccepted(document_id=str(existing.id), job_id="", duplicate=True)

    # 6. Declared metadata: parse + resolve field names against the schema (structural check
    #    only — types/required are the pipeline admission node's job).
    try:
        declared: dict = json.loads(metadata)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"metadata is not valid JSON: {exc}")
    schema = await CONTEXT.database.collections.get_schema(collection_id)
    by_name = {row.field_name: row for row in schema}
    unknown = sorted(set(declared) - set(by_name))
    if unknown:
        raise HTTPException(
            status_code=422, detail=f"Unknown metadata field(s) for this collection: {unknown}"
        )
    # Enum membership is STRUCTURAL — a declared value must be one of the field's declared set — so
    # it fails fast at the boundary alongside the unknown-field check (deeper value semantics, e.g.
    # datetime/list types, stay the admission node's job, per the pure-pipeline contract). Mirrors
    # AdmissionHelpers.value_error so the two never disagree on membership.
    enum_errors = [
        f"field '{name}' value {item!r} is not one of {by_name[name].enum_values}"
        for name, value in declared.items()
        if by_name[name].enum_values is not None
        for item in (value if isinstance(value, list) else [value])
        if item not in by_name[name].enum_values
    ]
    if enum_errors:
        raise HTTPException(status_code=422, detail="; ".join(enum_errors))
    field_ids = {row.field_name: row.id for row in schema}

    # 7. Store the ORIGINAL bytes BEFORE enqueueing (key = source_hash — the worker refetches).
    #    Trust the CONTENT sniff for format/mime, never the filename extension or the client-sent
    #    Content-Type: both are caller-controlled and routinely wrong (missing extension, a .txt that
    #    is really a PDF, a browser sending application/octet-stream). detect() already ran the same
    #    sniff for the format gate above, so the stored facts and the admission decision agree.
    filename = file.filename or "upload"
    mime = detected_mime or "application/octet-stream"
    await CONTEXT.database.ingestion.store_blobs(
        [S3Object(key=source_hash, data=content, content_type=mime)],
        [
            Blob(
                content_hash=source_hash,
                s3_key=source_hash,
                mime_type=mime,
                size_bytes=len(content),
                kind=BlobKind.ORIGINAL,
            )
        ],
    )

    # 8. Admission — document + job + declared metadata, ONE transaction.
    #    format/mime come from the content sniff (step 7), NOT the extension/client Content-Type.
    #    source_kind is a provisional DIGITAL_BORN: scanned/mixed detection is not yet wired into the
    #    IR (the parser does not surface a reliable per-page scan signal), so update_facts leaves it
    #    untouched. Do NOT read it as "confirmed native" until that detection lands.
    document = Document(
        collection_id=collection_id,
        source_hash=source_hash,
        filename=filename,
        format=detected_format,
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

    # 9. Hand over to the worker — the queue message carries IDS ONLY. The worker reads the
    #    collection's per-collection budget itself and applies it as the engine's run timeout.
    await CONTEXT.queue.enqueue_ingest(str(created.id), str(job.id))
    CONTEXT.logger.info(f"Admitted '{filename}' as {created.id} (job {job.id})")
    return UploadAccepted(document_id=str(created.id), job_id=str(job.id))


@router.patch(
    "/{document_id}/enabled",
    response_model=DocumentEnabledResponse,
    dependencies=[Depends(require(Capability.WRITE))],
)
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
    existed = await CONTEXT.database.enablement.set_document_enabled(document_id, patch.enabled)
    if not existed:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found.")

    # 2. Echo the applied state.
    return DocumentEnabledResponse(document_id=str(document_id), enabled=patch.enabled)


@router.post(
    "/{document_id}/reingest",
    response_model=UploadAccepted,
    status_code=202,
    dependencies=[Depends(require(Capability.WRITE))],
)
@auto_handle_errors
async def reingest_document(
    document_id: uuid.UUID,
    force: bool = Query(
        default=False,
        description="Bypass the stage cache and recompute every stage from scratch (no cache "
        "read/write). Use to rebuild after a code change that did not bump a node's CACHE_VERSION.",
    ),
) -> UploadAccepted:
    """
    Re-run ingestion on an existing document — no delete-and-re-upload.

    The original bytes are already stored (content-addressed) and the worker refetches them, so
    re-uploading the same file is refused as a duplicate; this re-processes the stored original with
    the collection's CURRENT pipeline (and the current engine) instead. The run is idempotent — the
    previous chunks/IR/pages are purged and the vectors overwritten — and the user-declared metadata
    survives. Poll the returned job for progress. ``force=true`` recomputes every stage (no cache).

    Returns:
        UploadAccepted: The document id and the new ingestion job id (202); 404 when unknown.
    """
    # 1. Create a fresh job on the existing document (reset to PENDING). None = unknown document.
    result = await CONTEXT.database.ingestion.reingest(document_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found.")

    # 2. Hand over to the worker — it refetches the original by source_hash and re-runs the pipeline,
    #    reading the collection's per-collection job budget itself for the engine's run timeout.
    document, job = result
    await CONTEXT.queue.enqueue_ingest(str(document.id), str(job.id), force=force)
    CONTEXT.logger.info(f"Re-ingest enqueued for {document.id} (job {job.id}, force={force})")
    return UploadAccepted(document_id=str(document.id), job_id=str(job.id))


__all__ = ["router"]
