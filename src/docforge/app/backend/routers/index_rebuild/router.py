# ====== Code Summary ======
# The rebuild_index router — POST /collections/{id}/rebuild-index admits a collection-level job that
# recreates the Qdrant store from the current schema (no content re-embed) and queues it (202).

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException

# ====== Internal Project Imports ======
from shared_libs.services.db.facades import (
    CollectionBusyError,
    IndexRebuildActiveError,
    RebuildUnsupportedError,
)

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import AuthPrincipal, AuthzGuard, Capability, require
from ...libs.index_rebuild import IndexRebuildGuards, RebuildIndexAccepted
from ...utils.error_handling import auto_handle_errors

router = APIRouter(tags=["collections"])


@router.post(
    "/collections/{collection_id}/rebuild-index",
    response_model=RebuildIndexAccepted,
    status_code=202,
)
@auto_handle_errors
async def rebuild_collection_index(
    collection_id: uuid.UUID,
    principal: AuthPrincipal = Depends(require(Capability.WRITE)),
) -> RebuildIndexAccepted:
    """
    Rebuild the collection's vector index from its current schema — no content re-embed.

    Declares the named vectors of fields made semantic/lexical after first ingest, then refills the
    metadata vectors from Postgres (the dense metadata VALUES go through the embed provider). Ingests
    are refused (409) while it runs.

    Returns:
        RebuildIndexAccepted: The job to poll (202); 404 unknown collection; 409
            ``rebuild_index_active`` / ``collection_busy`` / ``rebuild_unsupported_chunk_lexical``; 503 when it could not be queued.
    """
    # 1. Scope, then admit (FOR UPDATE on the collection row; the unique index backs the race).
    AuthzGuard.assert_collection_scope(principal, str(collection_id))
    try:
        job_id = await CONTEXT.database.index_rebuild.admit(collection_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except IndexRebuildActiveError as exc:
        raise IndexRebuildGuards.active_conflict(exc)
    except CollectionBusyError as exc:
        raise IndexRebuildGuards.busy_conflict(exc)
    except RebuildUnsupportedError as exc:
        raise IndexRebuildGuards.unsupported_conflict(exc)
    # 2. Queue it; an enqueue failure frees the lock (abandon) and surfaces as 503.
    try:
        await CONTEXT.queue.enqueue_rebuild_index(str(collection_id), str(job_id))
    except Exception as exc:
        await CONTEXT.database.jobs.abandon(job_id, f"Enqueue failed: {exc}")
        raise HTTPException(
            status_code=503,
            detail=f"The index rebuild of {collection_id} could not be queued; retry later.",
        )
    return RebuildIndexAccepted(collection_id=str(collection_id), job_id=str(job_id))


__all__ = ["router"]
