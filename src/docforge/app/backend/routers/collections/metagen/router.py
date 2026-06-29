# ====== Code Summary ======
# Per-collection metagen preview sub-resource: POST /api/v1/collections/{collection_id}/metagen/preview.
# A dry-run that validates a generated field's prompt by running ONE LLM call (per-collection
# URL+secret, never .env) over a persisted chunk's text or an ad-hoc sample — no persistence, no
# caching. All business logic lives in backend.libs.metagen; the router only resolves inputs from
# CONTEXT, delegates, and shapes the response. Mounted under /api/v1/collections/{collection_id}/metagen.

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.auth import Capability, require_capability
from backend.libs.metagen import MetagenPreviewError, MetagenPreviewService
from backend.libs.utils.error_handling import auto_handle_errors
from backend.routers.collections.metagen.models import (
    MetagenPreviewRequest,
    MetagenPreviewResponse,
)
from common_libs.domain.metadata import schema_field_dicts

# Previewing a metagen prompt is an affordance of the pipeline-config editor and incurs real LLM
# spend, so it is gated behind config.write (the same capability needed to persist the metagen
# config) — keeping token spend out of read-only principals' reach.
_WRITE = [Depends(require_capability(Capability.CONFIG_WRITE))]

router = APIRouter(tags=["collections"])


@router.post("/preview", response_model=MetagenPreviewResponse, dependencies=_WRITE)
@auto_handle_errors
async def preview_metagen(
    collection_id: uuid.UUID, body: MetagenPreviewRequest
) -> MetagenPreviewResponse:
    """
    Dry-run a generated field's metagen prompt over a chunk or an ad-hoc sample.

    Returns:
        MetagenPreviewResponse: The generated value + raw object + token/cost estimate.
    """
    # 1. Resolve the collection (404 when absent) — source of pipeline + metadata schema.
    collection = await _get_collection(collection_id)
    metadata_fields = schema_field_dicts(collection.metadata_fields)

    # 2. Resolve the content source: a persisted chunk (ownership-checked) or ad-hoc sample text.
    content_text, heading_path = await _resolve_content(collection_id, body)

    # 3. Delegate to the preview service (builds the chain + schema + one generate_json call).
    service = MetagenPreviewService(CONTEXT.RUNTIME_CONFIG)
    try:
        result = await service.preview(
            pipeline=collection.pipeline,
            metadata_fields=metadata_fields,
            field_name=body.field_name,
            content_text=content_text,
            heading_path=heading_path,
        )
    except MetagenPreviewError as exc:
        # 422 — the metagen config cannot produce a preview for this field (no target / not a
        # generated field / no LLM provider configured).
        CONTEXT.logger.warning(
            f"Metagen preview rejected (422): collection={collection_id} "
            f"field={body.field_name!r} error={exc}"
        )
        raise HTTPException(status_code=422, detail=str(exc))

    # 4. Shape the service result into the API response.
    return MetagenPreviewResponse(
        field_name=body.field_name,
        scope=result.scope,
        value=result.value,
        raw=result.raw,
        token_estimate=result.token_estimate,
        cost_estimate=result.cost_estimate,
        provider=result.provider,
        degraded=result.degraded,
    )


# --- Private helpers ---------------------------------------------------------


async def _get_collection(collection_id: uuid.UUID) -> Any:
    """Fetch the collection ORM object with its metadata schema (404 if missing)."""
    async with CONTEXT.postgres.session() as session:
        collection = await CONTEXT.collection_repo.get_by_id(session, collection_id)
    if collection is None:
        # 404 — preview requested for a collection that does not exist.
        CONTEXT.logger.warning(
            f"Metagen preview rejected (404 unknown collection): collection={collection_id}"
        )
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")
    return collection


async def _resolve_content(
    collection_id: uuid.UUID, body: MetagenPreviewRequest
) -> tuple[str, str]:
    """
    Resolve the (content_text, heading_path) to feed the preview from the request body.

    Args:
        collection_id (uuid.UUID): The owning collection (chunk ownership is enforced against it).
        body (MetagenPreviewRequest): The validated request (exactly one content source set).

    Returns:
        tuple[str, str]: The content text and the chunk heading breadcrumb (empty for sample text).

    Raises:
        HTTPException: 404 when the chunk is unknown or belongs to another collection.
    """
    # 1. Ad-hoc sample text — no chunk lookup, no heading.
    if body.chunk_id is None:
        return (body.sample_text or ""), ""

    # 2. Persisted chunk — fetch it, then verify its document belongs to this collection.
    async with CONTEXT.postgres.session() as session:
        chunk = await CONTEXT.chunk_repo.get_by_id(session, str(body.chunk_id))
        if chunk is None:
            CONTEXT.logger.warning(
                f"Metagen preview rejected (404 unknown chunk): collection={collection_id} "
                f"chunk={body.chunk_id}"
            )
            raise HTTPException(status_code=404, detail=f"Chunk {body.chunk_id} not found.")
        document = await CONTEXT.document_repo.get_by_id(session, str(chunk["document_id"]))
    if document is None or document.collection_id != collection_id:
        # 404 — the chunk's document is unknown OR lives in a different collection (scope mismatch).
        CONTEXT.logger.warning(
            f"Metagen preview rejected (404 chunk scope mismatch): collection={collection_id} "
            f"chunk={body.chunk_id}"
        )
        raise HTTPException(
            status_code=404,
            detail=f"Chunk {body.chunk_id} not found in collection {collection_id}.",
        )
    heading_path = (chunk.get("prov") or {}).get("heading_path", "") or ""
    return (chunk.get("raw_text") or ""), heading_path
