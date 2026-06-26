# ====== Code Summary ======
# Documents section: ingest / list / get / update / reingest / delete.
# Nested under collections/ — documents are a sub-resource.

# ====== Standard Library Imports ======
import hashlib
import json
import uuid
from pathlib import Path

# ====== Third-Party Library Imports ======
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sse_starlette.sse import EventSourceResponse

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.auth import (
    Capability,
    Principal,
    principal_grants_capability,
    require_capability,
    require_principal_sse,
)
from backend.libs.utils.error_handling import auto_handle_errors
from backend.libs.utils.sse import SseHelpers
from backend.routers.collections.documents.helpers import DocumentOps
from backend.routers.collections.documents.staleness import DocumentStaleness
from backend.routers.collections.documents.models import (
    DocumentDeleteResponse,
    DocumentListResponse,
    DocumentResponse,
    IngestResponse,
    MetadataUpdateRequest,
    MetadataUpdateResponse,
    ReingestRequest,
    ReingestResponse,
)
from common_libs.storage.s3.helpers import S3Helpers
from common_libs.config.admission import AdmissionValidator
from backend.routers.jobs.models import JobResponse

# Reads (list/get/stream) need the documents.read capability; ingest/update/reingest/delete mutate
# the collection's documents and need documents.write. Declared per-route so each endpoint is explicit.
_READ = [Depends(require_capability(Capability.DOCUMENTS_READ))]
_WRITE = [Depends(require_capability(Capability.DOCUMENTS_WRITE))]

router = APIRouter(tags=["documents"])


@router.post("/ingest", response_model=IngestResponse, status_code=202, dependencies=_WRITE)
@auto_handle_errors
async def ingest_document(
    collection_id: uuid.UUID,
    file: UploadFile = File(..., description="Document to ingest."),
    metadata: str | None = Form(default=None, description="Optional JSON metadata payload."),
) -> IngestResponse:
    """
    Admit a document into a collection and enqueue the pipeline (async).

    Runs the admission gate first (format + size + payload vs schema), dedups, uploads the
    original to S3, then enqueues the arq pipeline task.
    """
    file_bytes = await file.read()
    if not file_bytes:
        # 400 — empty upload. Cheapest guard, runs before any collection/format/dedup work.
        CONTEXT.logger.warning(
            f"Ingest rejected (400 empty file): collection={collection_id} filename={file.filename!r}"
        )
        raise HTTPException(status_code=400, detail=f"Uploaded file is empty.")
    source_hash = hashlib.sha256(file_bytes).hexdigest()

    async with CONTEXT.postgres.session() as session:
        collection = await CONTEXT.collection_repo.get_by_id(session, collection_id)
    if collection is None:
        # 404 — target collection does not exist (cannot admit into an unknown contract).
        CONTEXT.logger.warning(
            f"Ingest rejected (404 unknown collection): collection={collection_id} filename={file.filename!r}"
        )
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")

    filename = file.filename or "unknown"

    user_meta: dict = {}
    if metadata:
        try:
            user_meta = json.loads(metadata)
            if not isinstance(user_meta, dict):
                raise ValueError(f"Metadata must be a JSON object.")
        except (json.JSONDecodeError, ValueError) as exc:
            # 422 — metadata form field is not a valid JSON object (parse error or non-dict).
            CONTEXT.logger.warning(
                f"Ingest rejected (422 invalid metadata JSON): collection={collection_id} "
                f"filename={filename!r} error={exc}"
            )
            raise HTTPException(status_code=422, detail=f"Invalid metadata JSON: {exc}")

    issues = AdmissionValidator.validate(collection, filename, len(file_bytes), user_meta)
    if issues:
        # 415/413/422 — document-admissibility break (unsupported format / too large / schema
        # contract violation); the first issue's status drives the response code.
        CONTEXT.logger.warning(
            f"Ingest rejected ({issues[0]['status']} admissibility): collection={collection_id} "
            f"filename={filename!r} issues={issues}"
        )
        raise HTTPException(status_code=issues[0]["status"], detail={"issues": issues})

    ext = Path(filename).suffix.lstrip(".").lower()

    async with CONTEXT.postgres.session() as session:
        existing = await CONTEXT.document_repo.find_duplicate(
            session, collection_id=collection_id, source_hash=source_hash,
            pipeline_version=collection.pipeline_version,
        )
    if existing is not None:
        # Content-addressed dedup hit — same source_hash already ingested under this pipeline
        # version; short-circuit (no re-upload, no re-enqueue, no resource gate).
        CONTEXT.logger.info(
            f"Ingest dedup hit doc_id={existing.id} collection={collection_id} "
            f"filename={filename!r} status={existing.status}"
        )
        return IngestResponse(doc_id=existing.id, status=existing.status, duplicate=True)

    # Resource-admission gate (Brique D) — runs AFTER document-admissibility (415/413/422) and the
    # duplicate short-circuit, so a harmless re-upload is never rejected for capacity. Asks "can the
    # system accept MORE load right now?": 429 on queue/in-flight capacity.
    async with CONTEXT.postgres.session() as session:
        decision = await CONTEXT.resource_admitter.admit(
            session=session, collection=collection,
            queue_introspector=CONTEXT.queue_introspector, job_repo=CONTEXT.job_repo,
        )
    if not decision.admitted:
        # 429 — capacity (queue backlog / in-flight).
        # ResourceAdmitter.admit() already logs the rejection reason; no duplicate log here.
        raise HTTPException(status_code=decision.status_code, detail=decision.detail)

    await CONTEXT.s3.upload(S3Helpers.key_original(source_hash), file_bytes, "application/octet-stream")

    async with CONTEXT.postgres.session() as session:
        doc = await CONTEXT.document_repo.create(
            session, collection_id=collection_id, source_hash=source_hash, filename=filename,
            format=ext, file_size=len(file_bytes), pipeline_version=collection.pipeline_version,
            user_meta=user_meta,
        )
        doc_id = doc.id
    async with CONTEXT.postgres.session() as session:
        job = await CONTEXT.job_repo.create(session, document_id=doc_id, collection_id=collection_id)
        job_id = job.id

    await CONTEXT.arq_pool.enqueue_job(
        "run_pipeline_task", document_id=str(doc_id), source_hash=source_hash, filename=filename,
        pipeline_version=collection.pipeline_version, job_id=str(job_id), collection_id=str(collection_id),
    )
    CONTEXT.logger.info(f"Admitted doc_id={doc_id} job_id={job_id} filename={filename!r}")
    return IngestResponse(doc_id=doc_id, status="pending", duplicate=False, job_id=job_id)


@router.get("/list", response_model=DocumentListResponse, dependencies=_READ)
@auto_handle_errors
async def list_documents(
    collection_id: uuid.UUID,
    status: str | None = Query(default=None, description="Filter by document status."),
    limit: int = Query(default=100, ge=1, le=500, description="Page size (1–500)."),
    offset: int = Query(default=0, ge=0, description="Page offset."),
    sort_by: Literal["created_at", "filename", "status", "file_size"] = Query(
        default="created_at", description="Field to sort by."
    ),
    sort_order: Literal["asc", "desc"] = Query(default="desc", description="Sort direction."),
) -> DocumentListResponse:
    """List documents in a collection with optional filter, pagination, and sort."""
    async with CONTEXT.postgres.session() as session:
        collection = await CONTEXT.collection_repo.get_by_id(session, collection_id)
        if collection is None:
            raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")
        total = await CONTEXT.document_repo.count_by_collection(
            session, collection_id, status_filter=status
        )
        docs = await CONTEXT.document_repo.list_by_collection(
            session, collection_id,
            status_filter=status,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        # Config history → per-document staleness vs the CURRENT config (precise + reversible).
        versions = await CONTEXT.config_repo.list_versions(session, collection_id)
    version_index = DocumentStaleness.index_versions(versions)

    items: list[DocumentResponse] = []
    for d in docs:
        stale, reasons = DocumentStaleness.evaluate(collection, d.pipeline_version, version_index)
        items.append(
            DocumentResponse.model_validate(d).model_copy(
                update={"stale": stale, "stale_reasons": reasons}
            )
        )
    return DocumentListResponse(documents=items, total=total, limit=limit, offset=offset)


# NOTE: SSE route — returns an EventSourceResponse stream, so it intentionally has NO
# response_model (a live stream cannot be a Pydantic model). It MUST be declared before the
# dynamic "/{document_id}" route below, otherwise "stream" would be captured as a document id.
# Auth: a browser EventSource cannot send headers, so this route authenticates via
# require_principal_sse (header OR ?token=) instead of the header-only _READ gate, then performs the
# per-collection documents.read authorization in-body using the resolved principal.
@router.get("/stream")
@auto_handle_errors
async def stream_documents(
    collection_id: uuid.UUID,
    principal: Principal = Depends(require_principal_sse),
) -> EventSourceResponse:
    """
    Stream live job/stage updates for one collection's documents as Server-Sent Events.

    Replaces the 2 s polling in the Documents tab: only events whose payload targets this
    collection are forwarded.

    Args:
        collection_id (uuid.UUID): The collection whose document updates to stream.
        principal (Principal): The SSE-authenticated caller (header or ?token= query param).

    Returns:
        EventSourceResponse: Collection-scoped live event stream.

    Raises:
        HTTPException: 403 when the caller's key lacks documents.read on the collection.
    """
    # 1. Per-collection documents.read authorization (done in-body since the SSE auth dep replaces
    #    the capability gate). A full-access principal passes; a scoped key must grant documents.read.
    if not principal_grants_capability(principal, collection_id, Capability.DOCUMENTS_READ):
        # 403 — the key's scope does not grant documents.read on this collection.
        CONTEXT.logger.warning(
            f"Stream rejected (403 missing capability): user_id={principal.user_id} "
            f"collection={collection_id} required={Capability.DOCUMENTS_READ.value}"
        )
        raise HTTPException(
            status_code=403,
            detail="Your API key is not authorized for 'documents.read' on this collection.",
        )

    # 2. Filter the global bus down to events for this collection
    return SseHelpers.stream(
        CONTEXT.event_broadcaster,
        keepalive=CONTEXT.RUNTIME_CONFIG.SSE_KEEPALIVE_SECONDS,
        predicate=SseHelpers.collection_predicate(str(collection_id)),
    )


@router.get("/{document_id}", response_model=DocumentResponse, dependencies=_READ)
@auto_handle_errors
async def get_document(collection_id: uuid.UUID, document_id: uuid.UUID) -> DocumentResponse:
    """
    Full document record with aggregated pipeline state.

    Includes chunk/block counts, file availability (original / PDF / markdown),
    indexing status, and any pipeline error messages from failed jobs.
    """
    # 1. Load document — validates it belongs to this collection
    doc = await _get_document(collection_id, document_id)

    # 2. Aggregate chunk count, block count, stage run summary, and pipeline errors
    async with CONTEXT.postgres.session() as session:
        chunk_count = await CONTEXT.chunk_repo.count_by_document(session, document_id)
        block_count = await CONTEXT.document_repo.count_blocks(session, document_id)
        stage_summary = await CONTEXT.document_repo.get_stage_run_summary(session, document_id)
        jobs = await CONTEXT.job_repo.list_by_document(session, document_id)
        collection = await CONTEXT.collection_repo.get_by_id(session, collection_id)
        versions = await CONTEXT.config_repo.list_versions(session, collection_id)

    # Per-document staleness vs the collection's CURRENT config.
    stale, stale_reasons = (
        DocumentStaleness.evaluate(
            collection, doc.pipeline_version, DocumentStaleness.index_versions(versions)
        )
        if collection is not None else (False, [])
    )

    # Only surface errors when the document itself is stuck in a failed state.
    # A done document may have an older failed job in its history — that's noise, not an error.
    latest_failed = next((j for j in sorted(jobs, key=lambda j: j.created_at, reverse=True)
                          if j.status == "failed" and j.error), None)
    pipeline_errors = [latest_failed.error] if latest_failed and doc.status == "failed" else []

    # 3. PDF availability — simple content-addressed key, one S3 head-object call
    has_pdf = await CONTEXT.s3.exists(S3Helpers.key_pdf(doc.source_hash))

    # has_markdown: prefer implicit_meta.markdown_key (written by S1 even on node-cache hits)
    # over stage_run table (absent when the node cache served the result).
    implicit = doc.implicit_meta or {}
    has_markdown = bool(implicit.get("markdown_key")) or stage_summary.get("s1") == "done"

    # 4. Build enriched response — chain lineage is extracted from implicit_meta so the
    # frontend doesn't have to know that traces live inside the metadata blob.
    return DocumentResponse.model_validate(doc).model_copy(update={
        "chunk_count": chunk_count,
        "block_count": block_count,
        "has_original": True,
        "has_pdf": has_pdf,
        "has_markdown": has_markdown,
        # S4/S5/S6 are NOT node-cached, so they never write a stage_run row — `stage_summary`
        # only ever contains s0/s1/s2. The embed stage flushes its chain traces onto the document
        # on success, so their presence is the reliable "S6 embedded + indexed this doc" marker.
        "indexed": stage_summary.get("s6") == "done" or bool(implicit.get("embed_chain_traces")),
        "stale": stale,
        "stale_reasons": stale_reasons,
        "pipeline_errors": pipeline_errors,
        "quality_score": implicit.get("quality_score"),
        "chain_traces": list(implicit.get("chain_traces", []) or []),
        "embed_chain_traces": list(implicit.get("embed_chain_traces", []) or []),
        # Full job history (newest first) so the UI can show every ingestion / reingestion / retry
        # and retrace each one's outcome, stage, worker, timing and error.
        "jobs": [
            JobResponse.from_model(j)
            for j in sorted(jobs, key=lambda j: j.created_at, reverse=True)
        ],
    })


@router.post("/{document_id}/update", response_model=MetadataUpdateResponse, dependencies=_WRITE)
@auto_handle_errors
async def update_document(
    collection_id: uuid.UUID, document_id: uuid.UUID, body: MetadataUpdateRequest
) -> MetadataUpdateResponse:
    """
    Merge a metadata patch into a document's user metadata (a null value removes a key).

    The merged payload is re-validated against the collection schema (422 on a contract break).
    With reindex=true, only the changed fields are synced into the live index.
    """
    # 1. Resolve the document (must belong to this collection) + the collection schema
    doc = await _get_document(collection_id, document_id)
    async with CONTEXT.postgres.session() as session:
        collection = await CONTEXT.collection_repo.get_by_id(session, collection_id)
    if collection is None:
        # 404 — the owning collection vanished between document load and schema fetch.
        CONTEXT.logger.warning(
            f"Metadata update rejected (404 unknown collection): collection={collection_id} "
            f"document={document_id}"
        )
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")

    # 2. Merge + re-validate + persist + optional reindex (shared with batch)
    result = await DocumentOps.apply_metadata(collection, doc, body.metadata, body.reindex)
    if "issues" in result:
        # 422 — merged metadata breaks the collection schema contract (DocumentOps logged details).
        CONTEXT.logger.warning(
            f"Metadata update rejected (422 schema violation): collection={collection_id} "
            f"document={document_id} issues={result['issues']}"
        )
        raise HTTPException(status_code=422, detail={"issues": result["issues"]})

    # 3. Mutation succeeded — record exactly what changed and whether the live index was synced.
    CONTEXT.logger.info(
        f"Metadata updated document={document_id} collection={collection_id} "
        f"changed_fields={result.get('changed_fields')} reindexed={result.get('reindexed')}"
    )
    return MetadataUpdateResponse(id=document_id, **result)


@router.post("/{document_id}/reingest", response_model=ReingestResponse, status_code=202, dependencies=_WRITE)
@auto_handle_errors
async def reingest_document(
    collection_id: uuid.UUID, document_id: uuid.UUID, body: ReingestRequest
) -> ReingestResponse:
    """
    Re-enqueue the full pipeline for a document.

    The Merkle node cache keeps unchanged stages cheap unless ``force=True``,
    which drops all cached nodes and rebuilds from scratch.
    """
    # 1. Resolve the document (must belong to this collection)
    doc = await _get_document(collection_id, document_id)

    # 2. Enqueue via shared helper
    job_id = await DocumentOps.reingest(doc, force=body.force)

    return ReingestResponse(document_id=document_id, job_id=job_id, status="pending")


@router.delete("/{document_id}/delete", response_model=DocumentDeleteResponse, dependencies=_WRITE)
@auto_handle_errors
async def delete_document(collection_id: uuid.UUID, document_id: uuid.UUID) -> DocumentDeleteResponse:
    """
    Delete a document and all associated data (cascade across Postgres / Qdrant / S3).

    Postgres rows cascade (blocks/chunks/jobs + stage_run). The document's Qdrant points are
    removed. S3 blobs are deleted only when no other document references the same content-
    addressed source_hash.
    """
    # 1. Resolve the document (must belong to this collection)
    doc = await _get_document(collection_id, document_id)

    # 2. Cascade delete across Qdrant / Postgres / S3 (shared with batch)
    result = await DocumentOps.delete_cascade(collection_id, document_id, doc.source_hash)

    return DocumentDeleteResponse(deleted=True, id=document_id, **result)


# ─── Private helpers ─────────────────────────────────────────────────────────

async def _get_document(collection_id: uuid.UUID, document_id: uuid.UUID):
    """Load a document and ensure it belongs to the given collection, else raise 404."""
    async with CONTEXT.postgres.session() as session:
        doc = await CONTEXT.document_repo.get_by_id(session, document_id)
    if doc is None or doc.collection_id != collection_id:
        # 404 — document id is unknown OR belongs to a different collection (scope mismatch).
        CONTEXT.logger.warning(
            f"Document lookup rejected (404): document={document_id} collection={collection_id}"
        )
        raise HTTPException(
            status_code=404,
            detail=f"Document {document_id} not found in collection {collection_id}.",
        )
    return doc
