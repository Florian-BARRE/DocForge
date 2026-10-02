# ====== Code Summary ======
# The sync_document_metadata arq task — the lightweight per-document re-embed that follows a metadata
# VALUE edit (PATCH /documents/{id}/metadata). It re-embeds ONLY the document's short metadata VALUES
# into their named vectors (semantic dense / lexical sparse) on every one of its chunk points, via
# the MetaVectorSyncFacade — never the chunk CONTENT. The filterable payload repaint already ran
# synchronously in the request; this task re-runs it too (idempotent) so a single entry point fully
# reconciles the document's denormalised metadata. Enqueued only when a changed field is
# semantic/lexical; idempotent, safe to re-run.

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Internal Project Imports (worker) ======
from backend.context import CONTEXT


async def sync_document_metadata(ctx: dict[str, Any], document_id: str) -> dict[str, int]:
    """
    Re-embed a single document's metadata values after a value edit (no content re-embed).

    Args:
        ctx (dict): arq's context dict (unused — services live on CONTEXT).
        document_id (str): The document to re-sync (UUID as string; the queue carries strings).

    Returns:
        dict[str, int]: ``{"meta_points": n, "filter_points": m}`` — points patched per axis.
    """
    # 1. Re-embed the short metadata VALUES into their named vectors on every chunk point.
    document_uuid = uuid.UUID(document_id)
    meta_points = await CONTEXT.database.meta_vectors.sync_document_meta_vectors(document_uuid)
    # 2. Repaint the filterable payloads too (idempotent) so this one task fully reconciles the doc.
    filter_points = await CONTEXT.database.filters.sync_document_filter_payloads(document_uuid)
    CONTEXT.logger.info(
        f"Synced metadata for document {document_id}: "
        f"{meta_points} meta point(s), {filter_points} filter point(s)"
    )
    return {"meta_points": meta_points, "filter_points": filter_points}


__all__ = ["sync_document_metadata"]
