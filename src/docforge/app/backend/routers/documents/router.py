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
from shared_libs.services.db.facades import ReingestOutcome
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
from ...utils.ingest_enqueuer import IngestEnqueuer
from ...utils.pipeline_validation import PipelineBlobValidator
from ...utils.upload_reader import UploadReader
from .helpers import DocumentAdmissionHelpers
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
    #     node. TWO composing checks, both must pass:
    #       (a) content-truth (anti-spoof): the DETECTED format (content sniff, never the extension)
    #           must be accepted — a ``.pdf`` that is really HTML is caught here.
    #       (b) extension-declaration (anti-garbage): a PRESENT-but-foreign extension (e.g.
    #           ``badfile.xyz``) is rejected with a clear message instead of being silently bucketed
    #           as ``txt`` by the decodable-text fallback. An extensionless upload skips (b) and is
    #           decided by (a) alone. This makes a wrong file fail as cleanly as an oversized one.
    #     The admit-node content check stays as defence in depth.
    filename = file.filename or "upload"
    extension_error = DocumentAdmissionHelpers.extension_rejection(
        filename, collection.supported_formats
    )
    if extension_error is not None:
        raise HTTPException(status_code=422, detail=extension_error)
    detected_format, detected_mime = FormatProbeHelpers.detect(content, filename)
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
    admission = await CONTEXT.database.ingestion.admit(document, Job(), rows)
    # A concurrent upload of the SAME content+config may have won the unique-constraint race between
    # the dedup pre-check (step 5) and this insert. The façade resolved that to the already-admitted
    # document, so return the SAME idempotent duplicate response the pre-check returns — never a 500.
    if not admission.created:
        return UploadAccepted(document_id=str(admission.document.id), job_id="", duplicate=True)
    created, job = admission.document, admission.job

    # 9. Hand over to the worker — the queue message carries IDS ONLY. The worker reads the
    #    collection's per-collection budget itself and applies it as the engine's run timeout. A
    #    queue failure marks the just-committed job FAILED (never an orphan PENDING the reaper cannot
    #    see) and surfaces as a 503 so the caller knows the run was not queued — re-ingest to retry.
    enqueued = await IngestEnqueuer.enqueue(
        CONTEXT.queue, CONTEXT.database.jobs, str(created.id), str(job.id)
    )
    if not enqueued:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Document {created.id} was admitted but its ingestion could not be queued; the "
                f"job is marked failed. Re-ingest the document once the queue is reachable."
            ),
        )
    CONTEXT.logger.info(f"Admitted '{filename}' as {created.id} (job {job.id})")
    return UploadAccepted(document_id=str(created.id), job_id=str(job.id))


@router.patch(
    "/{document_id}/enabled",
    response_model=DocumentEnabledResponse,
)
@auto_handle_errors
async def set_document_enabled(
    document_id: uuid.UUID,
    patch: EnabledPatch,
    principal: AuthPrincipal = Depends(require(Capability.WRITE)),
) -> DocumentEnabledResponse:
    """
    Toggle a document's searchability (reversible, no re-ingest) — a single Postgres flag.

    Search excludes a disabled document's chunks via a bounded exclusion fed from this flag, so no
    Qdrant point is touched here (no per-chunk fan-out).

    Returns:
        DocumentEnabledResponse: The document id and its new state; 404 when the document is unknown.
    """
    # 1. The collection is not in the path, so the path-scope gate cannot see it — load the document
    #    to resolve its collection and enforce the caller's scope (404 unknown, 403 foreign) BEFORE
    #    mutating another tenant's searchability. Full-access keys no-op inside the guard.
    document = await CONTEXT.database.documents.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found.")
    AuthzGuard.assert_collection_scope(principal, str(document.collection_id))

    # 2. The facade flips documents.enabled; False means the UPDATE matched no row — the document was
    #    deleted in the race window between the scope pre-load and here (a concurrent delete / a
    #    collection-transfer rollback), so surface the 404 rather than a false-positive 200.
    existed = await CONTEXT.database.enablement.set_document_enabled(document_id, patch.enabled)
    if not existed:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found.")

    # 3. Echo the applied state.
    return DocumentEnabledResponse(document_id=str(document_id), enabled=patch.enabled)


@router.post(
    "/{document_id}/reingest",
    response_model=UploadAccepted,
    status_code=202,
)
@auto_handle_errors
async def reingest_document(
    document_id: uuid.UUID,
    force: bool = Query(
        default=False,
        description="Bypass the stage cache and recompute every stage from scratch (no cache "
        "read/write). Use to rebuild after a code change that did not bump a node's CACHE_VERSION.",
    ),
    principal: AuthPrincipal = Depends(require(Capability.WRITE)),
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
    # 1. The collection is not in the path — load the document to resolve its collection and enforce
    #    the caller's scope BEFORE minting a paid job, so a scoped key cannot spend another tenant's
    #    provider budget by id (404 unknown, 403 foreign; full-access keys no-op inside the guard).
    document = await CONTEXT.database.documents.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found.")
    AuthzGuard.assert_collection_scope(principal, str(document.collection_id))

    # 2. Admit a fresh run. NOT_FOUND = unknown document (404); ALREADY_ACTIVE = a run is already
    #    queued/executing (409) — minting a second concurrent job would interleave the two runs'
    #    Qdrant delete-by-document + upsert and strand orphan points, so refuse rather than duplicate.
    result = await CONTEXT.database.ingestion.reingest(document_id)
    if result.outcome is ReingestOutcome.NOT_FOUND:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found.")
    if result.outcome is ReingestOutcome.ALREADY_ACTIVE:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Document {document_id} already has an active ingestion job "
                f"({result.active_job_id}); wait for it to finish or cancel it before re-ingesting."
            ),
        )

    # 3. Hand over to the worker — it refetches the original by source_hash and re-runs the pipeline,
    #    reading the collection's per-collection job budget itself for the engine's run timeout. A
    #    queue failure marks the fresh job FAILED (never an orphan PENDING) and surfaces as a 503.
    document, job = result.document, result.job
    enqueued = await IngestEnqueuer.enqueue(
        CONTEXT.queue, CONTEXT.database.jobs, str(document.id), str(job.id), force=force
    )
    if not enqueued:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Re-ingestion of document {document.id} could not be queued; the job is marked "
                f"failed. Retry once the queue is reachable."
            ),
        )
    CONTEXT.logger.info(f"Re-ingest enqueued for {document.id} (job {job.id}, force={force})")
    return UploadAccepted(document_id=str(document.id), job_id=str(job.id))


__all__ = ["router"]
