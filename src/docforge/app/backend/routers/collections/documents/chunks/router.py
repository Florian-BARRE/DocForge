# ====== Code Summary ======
# Chunks section (spec — Chunks): list / get / update. list paginates a document's chunks; get
# fully materializes one; update manually corrects a chunk's text and (optionally) re-embeds its
# content vectors. Chunks are the atomic retrieval unit and the source of truth for raw_text.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException, Query

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.auth import Capability, require_capability
from backend.libs.utils.error_handling import auto_handle_errors
from backend.routers.collections.documents.chunks.models import (
    ChunkListResponse,
    ChunkResponse,
    ChunkUpdateRequest,
    ChunkUpdateResponse,
)

# Listing/reading chunks is part of documents.read; manually correcting a chunk (and optionally
# re-embedding it) mutates the indexed content and needs the dedicated chunks.write capability.
_READ = [Depends(require_capability(Capability.DOCUMENTS_READ))]
_WRITE = [Depends(require_capability(Capability.CHUNKS_WRITE))]

router = APIRouter(tags=["chunks"])


@router.get("/list", response_model=ChunkListResponse, dependencies=_READ)
@auto_handle_errors
async def list_chunks(
    collection_id: uuid.UUID,
    document_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> ChunkListResponse:
    """List a document's chunks (reading order) with pagination."""
    # 1. Document must belong to the collection
    await _require_document(collection_id, document_id)

    # 2. Fetch + paginate (chunks are typically few per doc; page in app layer)
    async with CONTEXT.postgres.session() as session:
        rows = await CONTEXT.chunk_repo.get_by_document(session, document_id)
    page = rows[offset : offset + limit]
    return ChunkListResponse(
        chunks=[_to_response(r) for r in page], total=len(rows), limit=limit, offset=offset
    )


@router.get("/{chunk_id}", response_model=ChunkResponse, dependencies=_READ)
@auto_handle_errors
async def get_chunk(
    collection_id: uuid.UUID, document_id: uuid.UUID, chunk_id: uuid.UUID
) -> ChunkResponse:
    """Full materialization of a chunk (raw_text, embed_text, provenance)."""
    row = await _require_chunk(document_id, chunk_id)
    return _to_response(row)


@router.post("/{chunk_id}/update", response_model=ChunkUpdateResponse, dependencies=_WRITE)
@auto_handle_errors
async def update_chunk(
    collection_id: uuid.UUID, document_id: uuid.UUID, chunk_id: uuid.UUID, body: ChunkUpdateRequest
) -> ChunkUpdateResponse:
    """
    Manually correct a chunk's text, optionally re-embedding its content vectors.

    At least one of raw_text/embed_text must be provided. With reindex=true the chunk's
    content_dense/content_bm25 vectors are re-embedded from the (new) embed_text — skipped with
    a warning when embedding/index is disabled.
    """
    # 1. Validate input + ownership
    if body.raw_text is None and body.embed_text is None:
        # 422 — empty patch: neither raw_text nor embed_text supplied, nothing to update.
        CONTEXT.logger.warning(
            f"Chunk update rejected (422 empty patch): collection={collection_id} "
            f"document={document_id} chunk={chunk_id}"
        )
        raise HTTPException(status_code=422, detail="Provide raw_text and/or embed_text to update.")
    await _require_document(collection_id, document_id)
    await _require_chunk(document_id, chunk_id)

    # 2. Persist the correction
    async with CONTEXT.postgres.session() as session:
        updated = await CONTEXT.chunk_repo.update(
            session, str(chunk_id), raw_text=body.raw_text, embed_text=body.embed_text
        )

    # 3. Optionally re-embed the content vectors
    reindexed, warning = False, None
    if body.reindex:
        if CONTEXT.metadata_indexer is None:
            warning = "Embedding/index disabled (S6) — Postgres updated only."
        else:
            await CONTEXT.metadata_indexer.reembed_content(
                str(collection_id), str(chunk_id), updated["embed_text"]
            )
            reindexed = True

    # 4. Mutation succeeded — log which fields were corrected and whether vectors were re-embedded.
    changed_fields = [
        name for name, value in (("raw_text", body.raw_text), ("embed_text", body.embed_text))
        if value is not None
    ]
    if body.reindex and not reindexed:
        CONTEXT.logger.warning(
            f"Chunk updated chunk={chunk_id} document={document_id} changed_fields={changed_fields} "
            f"reindex requested but skipped ({warning})"
        )
    else:
        CONTEXT.logger.info(
            f"Chunk updated chunk={chunk_id} document={document_id} "
            f"changed_fields={changed_fields} reindexed={reindexed}"
        )

    # str(id): the RETURNING clause yields a uuid.UUID, but ChunkUpdateResponse.id is a str and
    # Pydantic v2 does not coerce UUID -> str (it would 500 with a string_type error on a live row).
    return ChunkUpdateResponse(
        id=str(updated["id"]), raw_text=updated["raw_text"], embed_text=updated["embed_text"],
        reindexed=reindexed, warning=warning,
    )


# ─── Private helpers ─────────────────────────────────────────────────────────


async def _require_document(collection_id: uuid.UUID, document_id: uuid.UUID) -> None:
    """404 unless the document exists in this collection."""
    async with CONTEXT.postgres.session() as session:
        doc = await CONTEXT.document_repo.get_by_id(session, document_id)
    if doc is None or doc.collection_id != collection_id:
        # 404 — document id is unknown OR belongs to a different collection (scope mismatch).
        CONTEXT.logger.warning(
            f"Chunk document lookup rejected (404): document={document_id} collection={collection_id}"
        )
        raise HTTPException(
            status_code=404, detail=f"Document {document_id} not found in collection {collection_id}."
        )


async def _require_chunk(document_id: uuid.UUID, chunk_id: uuid.UUID) -> dict:
    """Load a chunk and ensure it belongs to the document, else 404."""
    async with CONTEXT.postgres.session() as session:
        row = await CONTEXT.chunk_repo.get_by_id(session, str(chunk_id))
    if row is None or str(row["document_id"]) != str(document_id):
        # 404 — chunk id is unknown OR belongs to a different document (scope mismatch).
        CONTEXT.logger.warning(
            f"Chunk lookup rejected (404): chunk={chunk_id} document={document_id}"
        )
        raise HTTPException(status_code=404, detail=f"Chunk {chunk_id} not found in document {document_id}.")
    return row


def _to_response(row: dict) -> ChunkResponse:
    """Map a chunk row dict to the API response model."""
    return ChunkResponse(
        id=str(row["id"]), document_id=str(row["document_id"]), config_hash=row["config_hash"],
        block_ids=list(row["block_ids"]) if row["block_ids"] else [], raw_text=row["raw_text"],
        embed_text=row["embed_text"], token_count=row["token_count"], strategy=row["strategy"],
        prov=row["prov"] if isinstance(row.get("prov"), dict) else {},
        parent_id=str(row["parent_id"]) if row.get("parent_id") else None,
    )
