# ====== Code Summary ======
# Per-collection resource-limits sub-resource (Brique D): GET the configured caps + live usage,
# and PUT to replace them. Limits are stored as dedicated collection columns (NOT in the pipeline
# JSON blob) so editing them never triggers reindex semantics. Mounted under
# /api/v1/collections/{collection_id}/limits.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.auth import require_collection_role
from backend.libs.utils.error_handling import auto_handle_errors
from backend.routers.collections.limits.models import (
    CollectionLimitsResponse,
    CollectionLimitsUpdateRequest,
)
from common_libs.storage.postgres.models import GrantRole

# Viewing the caps + live usage needs 'read'; editing resource limits is an admin policy change.
_READ = [Depends(require_collection_role(GrantRole.READ))]
_ADMIN = [Depends(require_collection_role(GrantRole.ADMIN))]

router = APIRouter(tags=["collections"])


async def _live_usage(collection_id: uuid.UUID) -> int:
    """
    Read the collection's current in-flight job count.

    Args:
        collection_id (uuid.UUID): Target collection.

    Returns:
        int: running + pending jobs for the collection.
    """
    # 1. Indexed count read scoped to the collection
    async with CONTEXT.postgres.session() as session:
        counts = await CONTEXT.job_repo.count_by_status(session, collection_id=collection_id)
    return counts.get("running", 0) + counts.get("pending", 0)


@router.get("", response_model=CollectionLimitsResponse, dependencies=_READ)
@auto_handle_errors
async def get_limits(collection_id: uuid.UUID) -> CollectionLimitsResponse:
    """
    Return the collection's configured resource limits and live usage.

    Returns:
        CollectionLimitsResponse: Cap + current in-flight.
    """
    # 1. Resolve the collection (404 when absent)
    async with CONTEXT.postgres.session() as session:
        collection = await CONTEXT.collection_repo.get_by_id(session, collection_id)
    if collection is None:
        # 404 — limits requested for a collection that does not exist.
        CONTEXT.logger.warning(f"Get limits rejected (404 unknown collection): collection={collection_id}")
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")

    # 2. Assemble cap + live usage
    in_flight = await _live_usage(collection_id)
    return CollectionLimitsResponse.from_state(collection, in_flight=in_flight)


@router.put("", response_model=CollectionLimitsResponse, dependencies=_ADMIN)
@auto_handle_errors
async def update_limits(
    collection_id: uuid.UUID, body: CollectionLimitsUpdateRequest
) -> CollectionLimitsResponse:
    """
    Replace the collection's resource limits (the cap; null clears it).

    Returns:
        CollectionLimitsResponse: The refreshed cap + live usage.
    """
    # 1. Apply the new cap (404 when the collection does not exist)
    async with CONTEXT.postgres.session() as session:
        collection = await CONTEXT.collection_repo.update_limits(
            session, collection_id,
            max_in_flight=body.max_in_flight,
        )
    if collection is None:
        # 404 — cannot set limits on a collection that does not exist.
        CONTEXT.logger.warning(f"Update limits rejected (404 unknown collection): collection={collection_id}")
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")

    # 2. Echo the updated cap with live usage
    in_flight = await _live_usage(collection_id)
    CONTEXT.logger.info(
        f"Updated limits for collection {collection_id}: max_in_flight={body.max_in_flight}"
    )
    return CollectionLimitsResponse.from_state(collection, in_flight=in_flight)
