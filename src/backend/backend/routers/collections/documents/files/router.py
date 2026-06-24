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
from common_libs.storage.s3.helpers import S3Helpers

router = APIRouter(tags=["files"])


@router.get("/original", response_model=PresignedUrlResponse)
@auto_handle_errors
async def get_original(collection_id: uuid.UUID, document_id: uuid.UUID) -> PresignedUrlResponse:
    """Pre-signed URL for the original uploaded file."""
    doc = await _require_done(document_id)
    return PresignedUrlResponse(url=await CONTEXT.s3.get_presigned_url(S3Helpers.key_original(doc.source_hash)))


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
            # 404 — no markdown key and no S1 fingerprint to derive one (S1 never produced markdown).
            CONTEXT.logger.warning(
                f"Markdown URL rejected (404 no key/fingerprint): collection={collection_id} "
                f"document={document_id}"
            )
            raise HTTPException(status_code=404, detail=f"Markdown not available for {document_id}.")
        key = S3Helpers.key_markdown(doc.source_hash, s1_fp)
    if not await CONTEXT.s3.exists(key):
        # 404 — derived markdown blob is absent from the object store.
        CONTEXT.logger.warning(
            f"Markdown URL rejected (404 blob missing): collection={collection_id} "
            f"document={document_id} key={key}"
        )
        raise HTTPException(status_code=404, detail=f"Markdown not available for {document_id}.")
    return PresignedUrlResponse(url=await CONTEXT.s3.get_presigned_url(key))


@router.get("/pdf", response_model=PresignedUrlResponse)
@auto_handle_errors
async def get_pdf(collection_id: uuid.UUID, document_id: uuid.UUID) -> PresignedUrlResponse:
    """Pre-signed URL for the canonical PDF artefact."""
    doc = await _require_done(document_id)
    return PresignedUrlResponse(url=await CONTEXT.s3.get_presigned_url(S3Helpers.key_pdf(doc.source_hash)))


@router.get("/figures/{block_id:path}", response_model=PresignedUrlResponse)
@auto_handle_errors
async def get_figure_crop(
    collection_id: uuid.UUID, document_id: uuid.UUID, block_id: str
) -> PresignedUrlResponse:
    """Pre-signed URL for a figure crop PNG produced by S1 (keyed by block_id)."""
    doc = await _require_done(document_id)
    key = S3Helpers.key_figure_crop(doc.source_hash, block_id)
    if not await CONTEXT.s3.exists(key):
        # 404 — no figure-crop blob stored for this block id (block is not a figure / S1 skipped it).
        CONTEXT.logger.warning(
            f"Figure crop URL rejected (404 blob missing): collection={collection_id} "
            f"document={document_id} block={block_id!r}"
        )
        raise HTTPException(status_code=404, detail=f"Figure crop not found for block {block_id!r}.")
    return PresignedUrlResponse(url=await CONTEXT.s3.get_presigned_url(key))


# ─── Private helpers ─────────────────────────────────────────────────────────

async def _require_done(document_id: uuid.UUID):
    """Fetch a document and require status=done, else 404/409."""
    async with CONTEXT.postgres.session() as session:
        doc = await CONTEXT.document_repo.get_by_id(session, document_id)
    if doc is None:
        # 404 — no document row with this id (the file endpoints do not scope by collection).
        CONTEXT.logger.warning(f"File artefact rejected (404 unknown document): document={document_id}")
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found.")
    if doc.status != "done":
        # 409 — document exists but its pipeline has not finished, so artefacts are not ready.
        CONTEXT.logger.warning(
            f"File artefact rejected (409 not done): document={document_id} status={doc.status!r}"
        )
        raise HTTPException(status_code=409, detail=f"Document {document_id} not done (status={doc.status!r}).")
    return doc
