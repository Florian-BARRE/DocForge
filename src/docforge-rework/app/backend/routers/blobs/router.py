# ====== Code Summary ======
# The blobs router — streams a content-addressed blob's BYTES with its registered mime type. This is
# the seam the explorer relies on: page renders and figure crops load as <img src>, the canonical PDF
# renders inline. Content-addressed, so one route serves every blob kind; the mime type comes from
# the blob registry (never guessed). No Pydantic response_model — the payload is raw bytes.

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException, Response

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import AuthPrincipal, AuthzGuard, Capability, require
from ...utils.error_handling import auto_handle_errors

router = APIRouter(prefix="/blobs", tags=["blobs"])


@router.get("/{content_hash}", response_class=Response)
@auto_handle_errors
async def get_blob(
    content_hash: str,
    principal: AuthPrincipal = Depends(require(Capability.READ)),
) -> Response:
    """
    Stream a blob's bytes with its registered mime type (page render, figure crop, PDF, original).

    Returns:
        Response: The raw bytes with the blob's stored media type; 404 when the hash is unknown.
    """
    # 1. A blob is content-addressed and has no single owner — a scoped key may reach it only
    #    through a collection it owns. Resolve its owning collections and gate the SCOPED key on
    #    them (a full-access key skips both the lookup and the check). An orphan/foreign blob
    #    resolves to no owned collection → 403, which also avoids an existence oracle.
    if not principal.is_full_access:
        collections = await CONTEXT.database.documents.collections_for_blob(content_hash)
        AuthzGuard.assert_any_collection_scope(principal, collections)

    # 2. The registry lookup + S3 fetch happen inside the facade (mime type comes from the row).
    result = await CONTEXT.database.documents.read_blob(content_hash)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Blob {content_hash} not found.")

    # 3. Stream the bytes verbatim with the registered media type — never a guessed one.
    data, mime_type = result
    return Response(content=data, media_type=mime_type)


__all__ = ["router"]
