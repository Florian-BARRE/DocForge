# ====== Code Summary ======
# The collection config-SNIPPET router — the granular counterpart of the whole-collection export.
# Unlike a `.dcexport` bundle (async, worker-built, carries data), a snippet is SYNCHRONOUS and
# config-only: it exports ONE slice of a collection's configuration (its ingest pipeline blob, its
# search blob, or its metadata schema) as a small, secret-masked, versioned JSON wrapper, and applies
# an inbound snippet of that same kind back onto a collection through the SAME machinery a PATCH uses.
# The route is orchestration only — shaping lives in SnippetHelpers (pure) and the store follow-through
# in SnippetApplier.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import AuthPrincipal, AuthzGuard, Capability, require
from ...utils.error_handling import auto_handle_errors
from .applier import SnippetApplier
from .helpers import SnippetHelpers
from .models import CollectionSnippet, SnippetImportResult, SnippetKind

router = APIRouter(tags=["snippets"])


@router.get(
    "/collections/{collection_id}/snippets/{kind}",
    response_model=CollectionSnippet,
    dependencies=[Depends(require(Capability.READ))],
)
@auto_handle_errors
async def export_snippet(collection_id: uuid.UUID, kind: SnippetKind) -> CollectionSnippet:
    """
    Export ONE slice of a collection's configuration as a portable, secret-masked, versioned snippet.

    A synchronous, config-only alternative to the whole-collection `.dcexport` bundle: the returned
    JSON is stamped with the current ``format_version`` + producing ``docforge_version`` and carries
    the requested slice as its ``body`` (a masked graph blob for ``pipeline`` / ``search``, or
    ``{"fields": [...]}`` for ``schema``). The ``collection_id`` path param is collection-scoped by
    the READ gate. The frontend saves the payload under the ``.dfsnippet`` extension.

    Returns:
        CollectionSnippet: The versioned, masked config slice (404 when the collection is unknown).
    """
    # 1. Existence first — an unknown collection is a 404, mirroring the other collection reads.
    collection = await CONTEXT.database.collections.get(collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")

    # 2. Shape the requested slice into a masked, versioned snippet (schema read only for ``schema``).
    schema = await CONTEXT.database.collections.get_schema(collection_id)
    return SnippetHelpers.build(kind, collection, schema, RUNTIME_CONFIG.FASTAPI_APP_VERSION)


@router.post(
    "/collections/{collection_id}/snippets/{kind}",
    response_model=SnippetImportResult,
)
@auto_handle_errors
async def apply_snippet(
    collection_id: uuid.UUID,
    kind: SnippetKind,
    snippet: CollectionSnippet,
    principal: AuthPrincipal = Depends(require(Capability.WRITE)),
) -> SnippetImportResult:
    """
    Apply an inbound config snippet onto an EXISTING collection (synchronous, config-only).

    The snippet is version-gated then kind-checked against the URL (the path ``kind`` is
    authoritative; a mismatched body is a 422), and applied through the SAME path a PATCH uses — a
    pipeline is healed+validated and may flag a reindex, a search graph is validated, a schema is
    diff-applied and the store reconciled. Masked provider secrets are restored from the target
    collection's stored blob by node id; secrets from a DIFFERENT collection stay masked and must be
    re-entered (a snippet is config, not a secret carrier).

    Returns:
        SnippetImportResult: The applied kind + whether a reindex is now required (404 unknown
        collection; 422 on a version/kind mismatch, a broken graph, or a malformed schema).
    """
    # 1. Existence first — every later step assumes the row (it is the secret-restore merge base).
    collection = await CONTEXT.database.collections.get(collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")

    # 2. Belt-and-suspenders scope check (require(WRITE) already scoped the path param).
    AuthzGuard.assert_collection_scope(principal, str(collection_id))

    # 3. Version-gate + kind-match the snippet against the URL, then take its raw body (422 on either).
    body = SnippetHelpers.unwrap(snippet, kind)

    # 4. Apply through the shared config-write machinery; a vector-slug collision is a 422 (mirrors PATCH).
    try:
        needs_reindex = await SnippetApplier.apply(collection, kind, body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Collection {collection_id}: {exc}")

    CONTEXT.logger.info(f"Applied {kind} snippet to collection {collection_id}")
    return SnippetImportResult(
        collection_id=str(collection_id), kind=kind, needs_reindex=needs_reindex
    )


__all__ = ["router"]
