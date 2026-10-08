# ====== Code Summary ======
# Collection contract read routes — the fleet list (with its server-computed health summary), the
# schema-driven contract-schema discovery, and one collection's contract. Registered FIRST by the
# collections router so the literal ``/contract-schema`` path wins over ``/{collection_id}``.

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import AuthPrincipal, AuthzGuard, Capability, require
from ...libs.collection_ref import CollectionRef
from ...utils.error_handling import auto_handle_errors
from .helpers import CollectionHelpers
from .models import CollectionContractSchemaResponse, CollectionListItem, CollectionModel
from .technical_view import CollectionTechnicalView

router = APIRouter(prefix="/collections", tags=["collections"])


@router.get(
    "",
    response_model=list[CollectionListItem],
)
@auto_handle_errors
async def list_collections(
    principal: AuthPrincipal = Depends(require(Capability.READ_TEXT)),
) -> list[CollectionListItem]:
    """
    Return every collection the caller may see, with its full schema AND a server-computed health
    summary.

    The health summary is rolled up through the SAME path the detail probe (`GET /{id}/health`) uses,
    so a fleet card's verdict + doc/vector counts + last-ingest can never disagree with the
    collection's own overview — and the front no longer fans out N live probes per page load.

    Returns:
        list[CollectionListItem]: The contracts the key is scoped to (schema included), each with its
        health summary. A scoped key sees only its own collections — never the whole fleet.
    """
    # 1. Rows + their schemas (collection counts stay small — the N+1 is fine here).
    collections = await CONTEXT.database.collections.list_all()

    # 1b. Scope filter — a fleet-wide read must not leak other tenants' contracts (base_urls, models,
    #     schema fields, estimate rates). None = full access (root / auth-off / wildcard key).
    allowed = AuthzGuard.scoped_collections(principal)
    if allowed is not None:
        collections = [c for c in collections if str(c.id) in allowed]

    # 2. Fresh, cheap counters for the WHOLE fleet — three BATCHED grouped queries, no N+1, no Qdrant.
    ids = [c.id for c in collections]
    doc_counts = await CONTEXT.database.documents.count_by_collections(ids)
    chunk_counts = await CONTEXT.database.documents.count_chunks_by_collections(ids)
    last_ingests = await CONTEXT.database.jobs.last_successful_ingest_at_by_collections(ids)

    # 3. Pure, structural-only health roll-up (no provider sweep) — the list's single source of truth,
    #    consistent with the detail overview's structural determination.
    summaries = CONTEXT.health_service.summarize_structural(
        collections,
        doc_counts=doc_counts,
        chunk_counts=chunk_counts,
        last_ingests=last_ingests,
    )

    # 4. Batch EVERY collection's schema in ONE query (no per-row ``get_schema`` N+1), then build each
    #    list row DIRECTLY from the row + its schema + summary — no to_model()→model_dump() re-splat,
    #    and masking skips the deepcopy for the secret-free stock blobs (_mask_for_list).
    schemas = await CONTEXT.database.collections.get_schemas_by_collections(ids)
    items = [CollectionHelpers.to_list_item(c, schemas[c.id], summaries[c.id]) for c in collections]

    # 5. A key without READ_TECHNICAL gets the lean contracts — pipeline/search blobs withheld.
    return CollectionTechnicalView.shape(items, principal)


@router.get(
    "/contract-schema",
    response_model=CollectionContractSchemaResponse,
    dependencies=[Depends(require(Capability.READ_TECHNICAL))],
)
@auto_handle_errors
async def get_contract_schema() -> CollectionContractSchemaResponse:
    """
    Discover the FULL collection-contract vocabulary — nothing has to be guessed.

    Serves three things, each straight from the canonical server source it validates against (never a
    hand-copied literal): ``config_schema`` (the identity/limits scalar contract, mirroring a node's
    ``config_schema`` so a new scalar field auto-surfaces in the UI), ``field_schema`` (one metadata
    ``FieldSpec`` — its ``$defs`` carry the ``field_type``/``origin``/``scope`` enums), and
    ``supported_format_tokens`` (the accepted upload tokens). A purely-HTTP client (e.g. the MCP)
    thus learns every valid value from the API instead of discovering it was wrong at a 422.

    Returns:
        CollectionContractSchemaResponse: The identity/limits schema + the field/format vocabulary.
    """
    # 1. Every part is derived from the SAME models the create/upload path validates against — no drift.
    return CollectionHelpers.contract_schema()


@router.get(
    "/{collection_id}",
    response_model=CollectionModel,
)
@auto_handle_errors
async def get_collection(
    collection_id: CollectionRef,
    principal: AuthPrincipal = Depends(require(Capability.READ_TEXT)),
) -> CollectionModel:
    """
    Return one collection's contract — the full one for a READ_TECHNICAL caller.

    Returns:
        CollectionModel: Identity, limits, schema and config blobs (``pipeline``/``search`` null
        when the caller lacks READ_TECHNICAL).
    """
    # 1. Load the row (404 when unknown).
    collection = await CONTEXT.database.collections.get(collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")

    # 2. Build the contract (+ the aliases targeting it), then withhold the blobs from a
    #    non-technical reader.
    model = CollectionHelpers.to_model(
        collection,
        await CONTEXT.database.collections.get_schema(collection_id),
        [vector for _, vector in await CONTEXT.database.index_state.missing(collection_id)],
        aliases=await CONTEXT.database.collection_aliases.names_for(collection_id),
    )
    return CollectionTechnicalView.shape([model], principal)[0]


__all__ = ["router"]
