# ====== Code Summary ======
# The collection transfer router — the API delivery for the export/import ENGINE (worker tasks +
# tracking façade). It creates a `collection_transfer` tracking row and enqueues the matching worker
# task (ids only on the wire), polls a transfer's status, and streams a completed export bundle back
# to the client behind auth. All heavy movement is the worker's; this router only opens transfers,
# reads their status, and delivers the finished bytes.

# ====== Standard Library Imports ======
import uuid
from datetime import UTC, datetime

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG
from shared_libs.services.db.postgresql.tables import TransferKind
from shared_libs.services.db.postgresql.tables import TransferStatus as TransferState

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import AuthPrincipal, AuthzGuard, Capability, require
from ...utils.error_handling import auto_handle_errors
from .helpers import TransferHelpers
from .models import TransferAccepted, TransferStatus

router = APIRouter(tags=["transfers"])

# The bytes of a `.dcexport` bundle are a tar, zstd-compressed by default. Per-bundle compression is
# not recorded on the row (a bundle is portable and may have been produced elsewhere), so the default
# codec's media type is served; the extension (.dcexport) is the authoritative container marker.
_BUNDLE_MEDIA_TYPE = "application/zstd"


@router.post(
    "/collections/{collection_id}/export",
    response_model=TransferAccepted,
    status_code=202,
)
@auto_handle_errors
async def export_collection(
    collection_id: uuid.UUID,
    principal: AuthPrincipal = Depends(require(Capability.READ)),
) -> TransferAccepted:
    """
    Open an asynchronous export of a whole collection into a portable `.dcexport` bundle.

    The ``collection_id`` path param is collection-scoped by the READ gate. A tracking row is created
    PENDING BEFORE the enqueue so the caller always has a pollable id, then the worker task is
    enqueued with ids only (the worker streams the collection, publishes the bundle to S3 and drives
    the row to DONE with the artifact reference the download endpoint reads).

    Returns:
        TransferAccepted: The transfer id + kind + status (202); 404 when the collection is unknown.
    """
    # 1. Existence first — an unknown collection is a 404 before any row is created or task enqueued.
    collection = await CONTEXT.database.collections.get(collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")

    # 2. Create the PENDING tracking row (kind=export, source collection id + name) BEFORE enqueue,
    #    so a poll is possible the instant this returns.
    row = await CONTEXT.database.transfer_tracker.create(
        TransferKind.EXPORT,
        collection_id=collection_id,
        collection_name=collection.name,
    )

    # 3. Hand over to the worker — the queue message carries IDS ONLY (no arq control kwarg).
    await CONTEXT.queue.enqueue_export(str(collection_id), str(row.id))
    CONTEXT.logger.info(f"Export opened for collection {collection_id} (transfer {row.id})")
    return TransferAccepted(transfer_id=str(row.id), kind=str(row.kind), status=str(row.status))


@router.post(
    "/collections/import",
    response_model=TransferAccepted,
    status_code=202,
)
@auto_handle_errors
async def import_collection(
    file: UploadFile = File(..., description="The .dcexport bundle to import."),
    target_name: str | None = Form(None, description="Optional name for the new collection."),
    principal: AuthPrincipal = Depends(require(Capability.CREATE)),
) -> TransferAccepted:
    """
    Import a `.dcexport` bundle as a BRAND-NEW collection (asynchronous, no recompute).

    The multipart bundle is streamed straight to an S3 staging key WITHOUT buffering the (possibly
    multi-GB) file in memory — it is spooled to a temp file in bounded windows, then published to S3
    with a known Content-Length. Only then is a PENDING tracking row created and the worker task
    enqueued (ids only); the worker downloads, validates and restores the bundle, driving the row to
    DONE with the new collection's id.

    Returns:
        TransferAccepted: The transfer id + kind + status (202).
    """
    # 1. Stage the upload in S3 under a fresh, collision-free key. This is the ONLY heavy step and it
    #    touches no DB — a client disconnect leaves at most an orphan staging object (GC-able), never
    #    a dangling tracking row. Streamed to disk then to S3, so RAM stays flat regardless of size.
    staging_key = f"{RUNTIME_CONFIG.IMPORT_STAGING_PREFIX}/{uuid.uuid4()}.dcexport"
    await TransferHelpers.stage_upload(
        file, staging_key, CONTEXT.database.transfer, RUNTIME_CONFIG.IMPORT_MAX_BUNDLE_BYTES
    )

    # 2. Create the PENDING tracking row (kind=import, the staged bundle's key) BEFORE enqueue.
    row = await CONTEXT.database.transfer_tracker.create(
        TransferKind.IMPORT,
        s3_key=staging_key,
    )

    # 3. Hand over to the worker — IDS/SCALARS ONLY on the wire (no arq control kwarg).
    await CONTEXT.queue.enqueue_import(
        staging_key, str(row.id), TransferHelpers.optional_form(target_name)
    )
    CONTEXT.logger.info(f"Import opened from {staging_key} (transfer {row.id})")
    return TransferAccepted(transfer_id=str(row.id), kind=str(row.kind), status=str(row.status))


@router.get("/transfers/{transfer_id}", response_model=TransferStatus)
@auto_handle_errors
async def get_transfer(
    transfer_id: uuid.UUID,
    principal: AuthPrincipal = Depends(require(Capability.READ)),
) -> TransferStatus:
    """
    Poll one transfer's live status — progress, stage, counts, error, and (done export) the artifact.

    Scope: an export is scoped to its source collection; a completed import is scoped to the new
    collection. An in-flight import has no collection yet, so it carries no source scope — its
    unguessable transfer id gates it until the produced collection id lands (then scope applies).

    Returns:
        TransferStatus: The transfer's status surface; 404 when the id is unknown.
    """
    # 1. Load the row (404 before any scope decision).
    row = await CONTEXT.database.transfer_tracker.get(transfer_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Transfer {transfer_id} not found.")

    # 2. Scope by the transfer's collection when one exists (export source, or import result).
    if row.collection_id is not None:
        AuthzGuard.assert_collection_scope(principal, str(row.collection_id))

    # 3. Serve the status surface.
    return TransferStatus.from_row(row)


@router.get("/transfers/{transfer_id}/download")
@auto_handle_errors
async def download_transfer(
    transfer_id: uuid.UUID,
    principal: AuthPrincipal = Depends(require(Capability.READ)),
) -> StreamingResponse:
    """
    Stream a completed EXPORT bundle from S3 to the client, behind auth, as an attachment.

    Only a DONE export with a live (non-expired) artifact is downloadable; anything else — an unknown
    id, an import, an unfinished/failed export, or an expired bundle — is a 404. The bytes are pulled
    from S3 in bounded chunks (never whole in memory) so a multi-GB bundle streams straight through.

    Returns:
        StreamingResponse: The bundle bytes as ``application/zstd`` with a filename attachment; 404
        when the transfer is not a downloadable export.
    """
    # 1. Load the row (404 before any scope decision).
    row = await CONTEXT.database.transfer_tracker.get(transfer_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Transfer {transfer_id} not found.")

    # 2. Downloadable only when it is a DONE export with a stored bundle key — otherwise 404 (an
    #    import, or an export not yet finished/failed, has nothing to hand back).
    is_export = row.kind == TransferKind.EXPORT
    is_done = row.status == TransferState.DONE
    if not (is_export and is_done and row.s3_key):
        raise HTTPException(
            status_code=404, detail=f"Transfer {transfer_id} has no downloadable export bundle."
        )

    # 3. Expired bundles are gone (the object may already be GC'd) — surface a clean 404, not a
    #    later S3 read error mid-stream.
    if row.expires_at is not None and row.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=404, detail=f"Transfer {transfer_id}'s bundle has expired.")

    # 4. Scope by the source collection (still present unless the collection was later deleted).
    if row.collection_id is not None:
        AuthzGuard.assert_collection_scope(principal, str(row.collection_id))

    # 5. Stream the bytes straight from S3 behind auth; the attachment filename leads with the name.
    filename = TransferHelpers.download_filename(row.collection_name, row.finished_at)
    return StreamingResponse(
        CONTEXT.database.transfer.stream_bundle(row.s3_key),
        media_type=_BUNDLE_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


__all__ = ["router"]
