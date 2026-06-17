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

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.utils.error_handling import auto_handle_errors
from backend.routers.collections.documents.helpers import DocumentOps
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
from admission import AdmissionValidator

router = APIRouter(tags=["documents"])


@router.post("/ingest", response_model=IngestResponse, status_code=202)
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
        raise HTTPException(status_code=400, detail=f"Uploaded file is empty.")
    source_hash = hashlib.sha256(file_bytes).hexdigest()

    async with CONTEXT.postgres.session() as session:
        collection = await CONTEXT.collection_repo.get_by_id(session, collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")

    filename = file.filename or "unknown"

    user_meta: dict = {}
    if metadata:
        try:
            user_meta = json.loads(metadata)
            if not isinstance(user_meta, dict):
                raise ValueError(f"Metadata must be a JSON object.")
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"Invalid metadata JSON: {exc}")

    issues = AdmissionValidator.validate(collection, filename, len(file_bytes), user_meta)
    if issues:
        raise HTTPException(status_code=issues[0]["status"], detail={"issues": issues})

    ext = Path(filename).suffix.lstrip(".").lower()

    async with CONTEXT.postgres.session() as session:
        existing = await CONTEXT.document_repo.find_duplicate(
            session, collection_id=collection_id, source_hash=source_hash,
            pipeline_version=collection.pipeline_version,
        )
    if existing is not None:
        return IngestResponse(doc_id=existing.id, status=existing.status, duplicate=True)

    await CONTEXT.s3.upload(CONTEXT.s3.key_original(source_hash), file_bytes, "application/octet-stream")

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


@router.get("/list", response_model=DocumentListResponse)
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
    return DocumentListResponse(
        documents=[DocumentResponse.model_validate(d) for d in docs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
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

    # Only surface errors when the document itself is stuck in a failed state.
    # A done document may have an older failed job in its history — that's noise, not an error.
    latest_failed = next((j for j in sorted(jobs, key=lambda j: j.created_at, reverse=True)
                          if j.status == "failed" and j.error), None)
    pipeline_errors = [latest_failed.error] if latest_failed and doc.status == "failed" else []

    # 3. PDF availability — simple content-addressed key, one S3 head-object call
    has_pdf = await CONTEXT.s3.exists(CONTEXT.s3.key_pdf(doc.source_hash))

    # has_markdown: prefer implicit_meta.markdown_key (written by S1 even on node-cache hits)
    # over stage_run table (absent when the node cache served the result).
    implicit = doc.implicit_meta or {}
    has_markdown = bool(implicit.get("markdown_key")) or stage_summary.get("s1") == "done"

    # 4. Build enriched response
    return DocumentResponse.model_validate(doc).model_copy(update={
        "chunk_count": chunk_count,
        "block_count": block_count,
        "has_original": True,
        "has_pdf": has_pdf,
        "has_markdown": has_markdown,
        "indexed": stage_summary.get("s6") == "done",
        "pipeline_errors": pipeline_errors,
    })


@router.post("/{document_id}/update", response_model=MetadataUpdateResponse)
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
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")

    # 2. Merge + re-validate + persist + optional reindex (shared with batch)
    result = await DocumentOps.apply_metadata(collection, doc, body.metadata, body.reindex)
    if "issues" in result:
        raise HTTPException(status_code=422, detail={"issues": result["issues"]})

    return MetadataUpdateResponse(id=document_id, **result)


@router.post("/{document_id}/reingest", response_model=ReingestResponse, status_code=202)
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


@router.delete("/{document_id}/delete", response_model=DocumentDeleteResponse)
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
        raise HTTPException(
            status_code=404,
            detail=f"Document {document_id} not found in collection {collection_id}.",
        )
    return doc
