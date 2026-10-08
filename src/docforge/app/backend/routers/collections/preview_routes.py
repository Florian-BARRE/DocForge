# ====== Code Summary ======
# Collection dry-run preview routes — run the ingest graph on ONE document without persisting
# anything: the inline fast-lane (API process) and the asynchronous worker-side submit + poll pair.
# Request shaping (blob parse, source resolution) lives in preview_helpers.py.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

# ====== Internal Project Imports ======
from shared_libs.pipelines.ingest import BlobNormalizationError

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import AuthPrincipal, AuthzGuard, Capability, require
from ...libs.collection_ref import CollectionRef
from ...libs.preview import PreviewGraphError, PreviewInputError, PreviewResponse
from ...utils.error_handling import auto_handle_errors
from .models import PreviewJobAccepted, PreviewJobResult
from .preview_helpers import CollectionPreviewHelpers

router = APIRouter(prefix="/collections", tags=["collections"])


@router.post(
    "/{collection_id}/pipeline/preview",
    response_model=PreviewResponse,
    dependencies=[Depends(require(Capability.WRITE)), Depends(require(Capability.READ_TECHNICAL))],
)
@auto_handle_errors
async def preview_pipeline(
    request: Request,
    collection_id: CollectionRef,
    principal: AuthPrincipal = Depends(require(Capability.WRITE)),
    file: UploadFile | None = File(
        None, description="The document to dry-run (omit to use document_id)."
    ),
    document_id: str | None = Form(
        None, description="An existing document to dry-run (omit to upload)."
    ),
    blob: str | None = Form(
        None, description="Optional candidate pipeline blob (JSON) to preview."
    ),
    metadata: str = Form(
        "{}", description="Declared metadata for an UPLOADED source (JSON object)."
    ),
    max_chunks: int | None = Form(None, description="How many preview chunks to return (capped)."),
) -> PreviewResponse:
    """
    Dry-run the ingestion pipeline on ONE document and return a bounded preview — NOTHING is persisted.

    Runs the INGEST graph inline (the same pure engine a real run uses) against either an uploaded
    file OR an already-ingested ``document_id``, optionally with a candidate ``blob`` instead of the
    collection's stored pipeline. Returns an IR summary, the first N chunks, the run's ACTUAL metered
    cost, and the full execution trace. No document row, S3 object or Qdrant point is written. The run
    is bounded by the interactive guardrails (PREVIEW_RUN_TIMEOUT_SECONDS wall-clock cap + PREVIEW_MAX_BYTES
    body cap). A node that fails is DATA (ok=false + the trace showing where it died), never a 500.

    Returns:
        PreviewResponse: The bounded dry-run report (404 unknown collection/document; 422 on a bad
        blob, a missing/oversized source, or neither/both of file and document_id supplied).
    """
    # 1. The collection must exist and be in the caller's scope (WRITE — a preview consumes provider spend).
    collection = await CONTEXT.database.collections.get(collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")
    AuthzGuard.assert_collection_scope(principal, str(collection_id))

    # 2. Exactly one source: an uploaded file XOR an existing document id.
    if (file is None) == (document_id is None):
        raise HTTPException(
            status_code=422, detail="Provide exactly one of 'file' or 'document_id'."
        )

    # 3. Parse the optional candidate blob (JSON object) + resolve the chunk ceiling.
    blob_override = CollectionPreviewHelpers.parse_blob(blob)
    ceiling = CONTEXT.RUNTIME_CONFIG.PREVIEW_MAX_CHUNKS
    effective_max_chunks = ceiling if max_chunks is None else max(0, min(max_chunks, ceiling))
    size_cap = min(collection.max_file_size_bytes, CONTEXT.RUNTIME_CONFIG.PREVIEW_MAX_BYTES)

    # 4. Build the SourceDocument: an uploaded body (read under the preview cap) or a rehydrated doc.
    try:
        source = await CollectionPreviewHelpers.resolve_source(
            file, document_id, metadata, collection_id, collection, request, size_cap
        )
    except PreviewInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # 5. Dry-run inline (no persistence). A bad blob is a 422; a failed node is DATA in the response.
    try:
        result = await CONTEXT.preview_service.preview(
            collection_id,
            source,
            max_chunks=effective_max_chunks,
            blob_override=blob_override,
            collection=collection,
        )
    except (PreviewGraphError, BlobNormalizationError) as exc:
        raise HTTPException(status_code=422, detail=f"Collection {collection_id}: {exc}")
    if result is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")
    return result


@router.post(
    "/{collection_id}/pipeline/preview/jobs",
    response_model=PreviewJobAccepted,
    status_code=202,
    dependencies=[Depends(require(Capability.WRITE)), Depends(require(Capability.READ_TECHNICAL))],
)
@auto_handle_errors
async def submit_preview_job(
    request: Request,
    collection_id: CollectionRef,
    principal: AuthPrincipal = Depends(require(Capability.WRITE)),
    file: UploadFile | None = File(
        None, description="The document to dry-run (omit to use document_id)."
    ),
    document_id: str | None = Form(
        None, description="An existing document to dry-run (omit to upload)."
    ),
    blob: str | None = Form(
        None, description="Optional candidate pipeline blob (JSON) to preview."
    ),
    metadata: str = Form(
        "{}", description="Declared metadata for an UPLOADED source (JSON object)."
    ),
    max_chunks: int | None = Form(None, description="How many preview chunks to return (capped)."),
) -> PreviewJobAccepted:
    """
    Submit an ASYNCHRONOUS worker-side dry-run preview — returns a pollable id, persists NOTHING.

    Unlike the inline ``/pipeline/preview`` fast-lane (which runs in the API process and cannot parse
    pipelines whose deps — docling — live only in the worker image), this enqueues a WORKER preview
    job that runs the full ingest graph with every dependency present, so it covers ALL pipelines. The
    uploaded bytes (capped at PREVIEW_MAX_BYTES) ride through the queue; an existing ``document_id`` is
    rehydrated worker-side from the store. The worker writes nothing durable and RETURNS the bounded
    report as the job result (kept in Redis with a TTL). Poll ``/pipeline/preview/jobs/{preview_id}``.

    Returns:
        PreviewJobAccepted: The preview id + initial status (202); 404 unknown collection/document;
        422 on a bad blob, a missing/oversized source, or neither/both of file and document_id.
    """
    # 1. The collection must exist and be in the caller's scope (WRITE — a preview consumes spend).
    collection = await CONTEXT.database.collections.get(collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")
    AuthzGuard.assert_collection_scope(principal, str(collection_id))

    # 2. Exactly one source: an uploaded file XOR an existing document id.
    if (file is None) == (document_id is None):
        raise HTTPException(
            status_code=422, detail="Provide exactly one of 'file' or 'document_id'."
        )

    # 3. Parse the optional candidate blob (JSON object).
    blob_override = CollectionPreviewHelpers.parse_blob(blob)
    size_cap = min(collection.max_file_size_bytes, CONTEXT.RUNTIME_CONFIG.PREVIEW_MAX_BYTES)

    # 4. Resolve the source payload carried to the worker: uploaded bytes read under the cap, OR an
    #    existing document id validated to exist in this collection (the worker rehydrates its bytes).
    (
        content,
        declared,
        filename,
        resolved_document_id,
    ) = await CollectionPreviewHelpers.resolve_submission(
        file, document_id, metadata, collection, request, size_cap
    )

    # 5. Enqueue the worker preview job keyed by a fresh preview id, then return it for polling.
    preview_id = uuid.uuid4().hex
    await CONTEXT.queue.enqueue_preview(
        preview_id,
        str(collection_id),
        resolved_document_id,
        content,
        declared,
        filename,
        blob_override,
        max_chunks,
    )
    return PreviewJobAccepted(preview_id=preview_id, status="pending")


@router.get(
    "/{collection_id}/pipeline/preview/jobs/{preview_id}",
    response_model=PreviewJobResult,
    dependencies=[Depends(require(Capability.WRITE)), Depends(require(Capability.READ_TECHNICAL))],
)
@auto_handle_errors
async def get_preview_job(
    collection_id: CollectionRef,
    preview_id: str,
    principal: AuthPrincipal = Depends(require(Capability.WRITE)),
) -> PreviewJobResult:
    """
    Poll an asynchronous dry-run preview by its id — the bounded report appears once status is 'done'.

    A failed NODE is DATA: status 'done' with ``result.ok`` = false (never a 500). 'failed' is reserved
    for the rare case the worker job itself crashed/timed out. An unknown or expired id is a 404.

    Returns:
        PreviewJobResult: status + (the report when done); 404 when the collection is out of scope or
        the preview id is unknown/expired.
    """
    # 1. Scope the collection (the id is in the path; a preview is a WRITE-scoped operation).
    collection = await CONTEXT.database.collections.get(collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")
    AuthzGuard.assert_collection_scope(principal, str(collection_id))

    # 2. Read the arq job state + result (the result is the PreviewResponse dict when complete).
    status, result, error = await CONTEXT.queue.get_preview_result(preview_id)
    if status == "not_found":
        raise HTTPException(status_code=404, detail=f"Preview {preview_id} not found or expired.")
    return PreviewJobResult(
        preview_id=preview_id,
        status=status,
        result=PreviewResponse(**result) if result is not None else None,
        error=error,
    )


__all__ = ["router"]
