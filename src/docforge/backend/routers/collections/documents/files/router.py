# ====== Code Summary ======
# Document file artefacts: original / markdown / pdf as pre-signed URLs.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, HTTPException

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.utils.error_handling import auto_handle_errors
from backend.routers.collections.documents.files.models import PresignedUrlResponse

router = APIRouter(tags=["files"])


@router.get("/original", response_model=PresignedUrlResponse)
@auto_handle_errors
async def get_original(collection_id: uuid.UUID, document_id: uuid.UUID) -> PresignedUrlResponse:
    """Pre-signed URL for the original uploaded file."""
    doc = await _require_done(document_id)
    return PresignedUrlResponse(url=await CONTEXT.s3.get_presigned_url(CONTEXT.s3.key_original(doc.source_hash)))


@router.get("/markdown", response_model=PresignedUrlResponse)
@auto_handle_errors
async def get_markdown(collection_id: uuid.UUID, document_id: uuid.UUID) -> PresignedUrlResponse:
    """Pre-signed URL for the faithful Markdown view produced by S1."""
    doc = await _require_done(document_id)
    implicit = doc.implicit_meta or {}
    key = implicit.get("markdown_key")
    if not key:
        s1_fp = implicit.get("s1_fingerprint")
        if not s1_fp:
            raise HTTPException(status_code=404, detail=f"Markdown not available for {document_id}.")
        key = CONTEXT.s3.key_markdown(doc.source_hash, s1_fp)
    if not await CONTEXT.s3.exists(key):
        raise HTTPException(status_code=404, detail=f"Markdown not available for {document_id}.")
    return PresignedUrlResponse(url=await CONTEXT.s3.get_presigned_url(key))


@router.get("/pdf", response_model=PresignedUrlResponse)
@auto_handle_errors
async def get_pdf(collection_id: uuid.UUID, document_id: uuid.UUID) -> PresignedUrlResponse:
    """Pre-signed URL for the canonical PDF artefact."""
    doc = await _require_done(document_id)
    return PresignedUrlResponse(url=await CONTEXT.s3.get_presigned_url(CONTEXT.s3.key_pdf(doc.source_hash)))


@router.get("/figures/{block_id:path}", response_model=PresignedUrlResponse)
@auto_handle_errors
async def get_figure_crop(
    collection_id: uuid.UUID, document_id: uuid.UUID, block_id: str
) -> PresignedUrlResponse:
    """Pre-signed URL for a figure crop PNG produced by S1 (keyed by block_id)."""
    doc = await _require_done(document_id)
    key = CONTEXT.s3.key_figure_crop(doc.source_hash, block_id)
    if not await CONTEXT.s3.exists(key):
        raise HTTPException(status_code=404, detail=f"Figure crop not found for block {block_id!r}.")
    return PresignedUrlResponse(url=await CONTEXT.s3.get_presigned_url(key))


# ─── Private helpers ─────────────────────────────────────────────────────────

async def _require_done(document_id: uuid.UUID):
    """Fetch a document and require status=done, else 404/409."""
    async with CONTEXT.postgres.session() as session:
        doc = await CONTEXT.document_repo.get_by_id(session, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found.")
    if doc.status != "done":
        raise HTTPException(status_code=409, detail=f"Document {document_id} not done (status={doc.status!r}).")
    return doc
