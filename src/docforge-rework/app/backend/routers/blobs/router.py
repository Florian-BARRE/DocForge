# ====== Code Summary ======
# The blobs router — streams a content-addressed blob's BYTES with its registered mime type. This is
# the seam the explorer relies on: page renders and figure crops load as <img src>, the canonical PDF
# renders inline. Content-addressed, so one route serves every blob kind; the mime type comes from
# the blob registry (never guessed). No Pydantic response_model — the payload is raw bytes.

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException, Response

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import Capability, require
from ...utils.error_handling import auto_handle_errors

router = APIRouter(prefix="/blobs", tags=["blobs"])


@router.get("/{content_hash}", response_class=Response, dependencies=[Depends(require(Capability.READ))])
@auto_handle_errors
async def get_blob(content_hash: str) -> Response:
    """
    Stream a blob's bytes with its registered mime type (page render, figure crop, PDF, original).

    Returns:
        Response: The raw bytes with the blob's stored media type; 404 when the hash is unknown.
    """
    # 1. The registry lookup + S3 fetch happen inside the facade (mime type comes from the row).
    result = await CONTEXT.database.documents.read_blob(content_hash)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Blob {content_hash} not found.")

    # 2. Stream the bytes verbatim with the registered media type — never a guessed one.
    data, mime_type = result
    return Response(content=data, media_type=mime_type)


__all__ = ["router"]
