# ====== Code Summary ======
# The collection-scoped stage edit — POST /collections/{id}/pipeline/stages/apply. The convenience twin
# of the stateless /pipelines/ingest/stages/apply: instead of the caller compiling an action on a blob
# it holds and PATCHing the whole blob back (secrets masked, easy to wipe), the server applies the ONE
# action to the collection's stored pipeline and persists it through the PATCH's write path. WRITE +
# READ_TECHNICAL (the response is a stage view of the pipeline), collection-scoped by the path param;
# the orchestration lives in CollectionStageApplier.

# ====== Standard Library Imports ======

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException

# ====== Internal Project Imports ======
from shared_libs.pipelines.blob_secrets import SecretReentryRequired

# ====== Local Project Imports ======
from ...libs.auth import AuthPrincipal, AuthzGuard, Capability, require
from ...libs.collection_ref import CollectionRef
from ...libs.config_history import ConfigAuthorResolver
from ...utils.error_handling import auto_handle_errors
from .models import CollectionStageApplyRequest, CollectionStageApplyResponse
from .service import CollectionStageApplier

router = APIRouter(prefix="/collections", tags=["collections"])


@router.post(
    "/{collection_id}/pipeline/stages/apply",
    response_model=CollectionStageApplyResponse,
    # The response IS the stage view of the pipeline (technical by nature) — demand READ_TECHNICAL.
    dependencies=[Depends(require(Capability.READ_TECHNICAL))],
)
@auto_handle_errors
async def apply_collection_stage(
    collection_id: CollectionRef,
    request: CollectionStageApplyRequest,
    principal: AuthPrincipal = Depends(require(Capability.WRITE)),
) -> CollectionStageApplyResponse:
    """
    Apply one stage action to a collection's stored ingestion pipeline and persist a valid result.

    The stored pipeline is the base (its real secrets included), so ``set_config`` with
    ``mode="merge"`` changes only the keys sent; secrets resolve exactly like a PATCH (a masked or
    omitted secret keeps the same provider's stored key at the same endpoint, an explicit ``""`` —
    or ``null`` in merge mode — clears it; a masked/omitted secret whose provider endpoint changed is
    refused with a 422 so the key is re-entered, never carried to the new host). A valid,
    changed result is stored through the PATCH's write path (a new config version); an invalid
    result or a no-op is returned as data with ``persisted=false`` and nothing is written.

    Returns:
        CollectionStageApplyResponse: The redacted stage view + validity + notices + persist verdict;
        404 unknown collection, 403 outside the caller's scope, 422 unmigratable stored pipeline or
        a secret that must be re-entered after an endpoint change, 409 when concurrent config writes kept changing the pipeline under the action.
    """
    # 1. Belt-and-suspenders scope check (require(WRITE) already scoped the path param).
    AuthzGuard.assert_collection_scope(principal, str(collection_id))

    # 2. Read head → apply → validate → CAS-persist (only a valid change is written; 404 if absent).
    try:
        return await CollectionStageApplier.apply(
            collection_id, request, ConfigAuthorResolver.from_principal(principal)
        )
    except SecretReentryRequired as exc:
        raise HTTPException(status_code=422, detail=f"Collection {collection_id}: {exc}")


__all__ = ["router"]
