# ====== Code Summary ======
# The document-READING router — how an agent reads a document piecemeal instead of all at once:
# GET /documents/{id}/outline (the heading outline, each heading linked to its section's first chunk)
# and GET /chunks/{id}/context (a chunk with its enabled neighbours by chunk_index). Both are
# READ-capability routes with the explorer's collection-scope gate (by the document's own collection);
# the reads and shaping live in CONTEXT.document_reader.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException, Query

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import AuthPrincipal, AuthzGuard, Capability, require
from ...libs.reading import ChunkContext, DocumentOutline
from ...utils.error_handling import auto_handle_errors

router = APIRouter(tags=["explorer"])

# Upper bound of the neighbours taken on each side of a context window.
_MAX_CONTEXT_NEIGHBOURS = 5


@router.get("/documents/{document_id}/outline", response_model=DocumentOutline)
@auto_handle_errors
async def get_document_outline(
    document_id: uuid.UUID,
    principal: AuthPrincipal = Depends(require(Capability.READ)),
) -> DocumentOutline:
    """
    Return a document's heading outline — level, text, 1-based page and section-opening chunk.

    Returns:
        DocumentOutline: The outline (headings in reading order); 404 when the document is unknown,
        403 when it is outside the caller's collection scope.
    """
    # 1. Existence first (404), then the scope of the document's own collection (403).
    document = await CONTEXT.document_reader.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found.")
    AuthzGuard.assert_collection_scope(principal, str(document.collection_id))

    # 2. Build the outline from the lean heading + chunk-index reads.
    return await CONTEXT.document_reader.outline(document)


@router.get("/chunks/{chunk_id}/context", response_model=ChunkContext)
@auto_handle_errors
async def get_chunk_context(
    chunk_id: uuid.UUID,
    before: int = Query(
        default=1,
        ge=0,
        le=_MAX_CONTEXT_NEIGHBOURS,
        description="Searchable chunks to include before the target (0-5).",
    ),
    after: int = Query(
        default=1,
        ge=0,
        le=_MAX_CONTEXT_NEIGHBOURS,
        description="Searchable chunks to include after the target (0-5).",
    ),
    principal: AuthPrincipal = Depends(require(Capability.READ)),
) -> ChunkContext:
    """
    Return a chunk with its neighbours by chunk_index in the same document (disabled ones skipped).

    Returns:
        ChunkContext: The ordered window, the requested chunk flagged ``is_target``; 404 when the
        chunk is unknown, 403 when its collection is outside the caller's scope.
    """
    # 1. Existence first (404), then the scope of the owning document's collection (403).
    located = await CONTEXT.document_reader.locate_chunk(chunk_id)
    if located is None:
        raise HTTPException(status_code=404, detail=f"Chunk {chunk_id} not found.")
    chunk, document = located
    AuthzGuard.assert_collection_scope(principal, str(document.collection_id))

    # 2. The window around it.
    return await CONTEXT.document_reader.chunk_context(chunk, document, before, after)


__all__ = ["router"]
