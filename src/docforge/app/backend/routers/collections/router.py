# ====== Code Summary ======
# The collections router — the contract's CRUD: create (schema declared up front + pipeline
# blob seeded with the product default), read, patch the config blobs (pipeline VALIDATED
# before storage — a broken graph never reaches the worker), delete, plus the schema-driven
# discovery of the identity/limits contract. Every rejection carries an explicit HTTP code and a
# precise message. Non-route logic lives in helpers.py (pure) and store_sync.py (store follow-through).

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql.tables import Collection

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import AuthPrincipal, Capability, require
from ...libs.health import CollectionHealthResponse
from ...utils.error_handling import auto_handle_errors
from .helpers import CollectionHelpers
from .models import (
    CollectionContractModel,
    CollectionContractSchemaResponse,
    CollectionModel,
    CreateCollectionRequest,
    UpdateCollectionRequest,
)
from .redaction import restore_blob_secrets
from .store_sync import CollectionStoreSync

router = APIRouter(prefix="/collections", tags=["collections"])


@router.get(
    "",
    response_model=list[CollectionModel],
    dependencies=[Depends(require(Capability.READ))],
)
@auto_handle_errors
async def list_collections() -> list[CollectionModel]:
    """
    Return every collection with its full schema.

    Returns:
        list[CollectionModel]: All contracts, schema included.
    """
    # 1. Rows + their schemas (collection counts stay small — the N+1 is fine here).
    collections = await CONTEXT.database.collections.list_all()
    return [
        CollectionHelpers.to_model(c, await CONTEXT.database.collections.get_schema(c.id))
        for c in collections
    ]


@router.get(
    "/contract-schema",
    response_model=CollectionContractSchemaResponse,
    dependencies=[Depends(require(Capability.READ))],
)
@auto_handle_errors
async def get_contract_schema() -> CollectionContractSchemaResponse:
    """
    Discover the collection identity/limits contract as JSON Schema — the schema-driven UI form.

    Mirrors a node's ``config_schema`` face so a new scalar contract field auto-surfaces in the UI
    with zero frontend change (the frontend feeds it straight to its existing ``SchemaForm``).

    Returns:
        CollectionContractSchemaResponse: The ``model_json_schema()`` of the identity/limits contract.
    """
    # 1. The schema is derived from the SAME model CreateCollectionRequest composes — no drift.
    return CollectionContractSchemaResponse(
        config_schema=CollectionContractModel.model_json_schema()
    )


@router.get(
    "/{collection_id}",
    response_model=CollectionModel,
    dependencies=[Depends(require(Capability.READ))],
)
@auto_handle_errors
async def get_collection(collection_id: uuid.UUID) -> CollectionModel:
    """
    Return one collection's full contract.

    Returns:
        CollectionModel: Identity, limits, schema and config blobs.
    """
    collection = await CONTEXT.database.collections.get(collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")
    return CollectionHelpers.to_model(
        collection, await CONTEXT.database.collections.get_schema(collection_id)
    )


@router.get(
    "/{collection_id}/health",
    response_model=CollectionHealthResponse,
    dependencies=[Depends(require(Capability.READ))],
)
@auto_handle_errors
async def get_collection_health(collection_id: uuid.UUID) -> CollectionHealthResponse:
    """
    Probe a collection's operational health on demand — provider reachability across the ingest AND
    search graphs, index population and last successful ingest — WITHOUT enqueuing a job or spending.

    Returns:
        CollectionHealthResponse: Per-provider reachability, index stats and a rolled-up verdict.
    """
    # 1. Compose the snapshot from the shared build + reachability + index reads (no writes).
    result = await CONTEXT.health_service.check(collection_id)

    # 2. Unknown collection → 404, mirroring the other collection reads.
    if result is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")
    return result


@router.post(
    "",
    response_model=CollectionModel,
    status_code=201,
)
@auto_handle_errors
async def create_collection(
    request: CreateCollectionRequest,
    principal: AuthPrincipal = Depends(require(Capability.CREATE)),
) -> CollectionModel:
    """
    Create a collection from A to Z — contract + full schema + pipeline blob.

    Requires the CREATE capability. A scoped key that creates a collection is auto-granted ownership
    of it: the new id is appended to the key's own ``collections`` scope, so the same key can then
    fully manage what it just created (per its other capabilities) without knowing ids in advance.

    Returns:
        CollectionModel: The created contract (201); 409 on name clash, 422 on bad
        pipeline or colliding vector slugs.
    """
    # 1. Name unicity — explicit 409, not a driver error.
    if await CONTEXT.database.collections.get_by_name(request.name) is not None:
        raise HTTPException(status_code=409, detail=f"Collection '{request.name}' already exists.")

    CollectionHelpers.validate_fields(request.fields)

    # 2. The pipeline blob: the caller's explicit graph wins; otherwise the stock blob the ``preset``
    #    selects (light = enrichment-free core). Healed to the current engine, validated and stamped.
    blob = CollectionHelpers.canonical_pipeline(
        request.pipeline or CollectionHelpers.preset_blob(request.preset)
    )

    # 3. Create contract + schema in one transaction (slug collisions → explicit 422).
    rows = CollectionHelpers.to_field_rows(request.fields)
    try:
        created = await CONTEXT.database.collections.create(
            Collection(
                name=request.name,
                supported_formats=request.supported_formats,
                max_file_size_bytes=request.max_file_size_bytes,
                job_timeout_seconds=request.job_timeout_seconds,
                pipeline=blob,
                search={},
            ),
            rows,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # 4. Ownership: a scoped, list-scoped key that just created this collection is granted access to
    #    it by appending the id to its own scope (root / wildcard keys already cover everything).
    await CollectionStoreSync.grant_creator_scope(principal, str(created.id))

    CONTEXT.logger.info(f"Collection '{request.name}' created ({len(rows)} fields)")
    return CollectionHelpers.to_model(
        created, await CONTEXT.database.collections.get_schema(created.id)
    )


@router.patch(
    "/{collection_id}",
    response_model=CollectionModel,
    dependencies=[Depends(require(Capability.WRITE))],
)
@auto_handle_errors
async def update_collection(
    collection_id: uuid.UUID, request: UpdateCollectionRequest
) -> CollectionModel:
    """
    Patch identity/limits, the metadata schema (by DIFF), and/or the config blobs.

    Returns:
        CollectionModel: The updated contract; 404 unknown, 409 name clash, 422 broken
        pipeline or colliding vector slugs.
    """
    # 1. Existence first — every later step assumes the row.
    current = await CONTEXT.database.collections.get(collection_id)
    if current is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")

    # 2. Renaming keeps names unique — explicit 409, not a driver error.
    if request.name is not None and request.name != current.name:
        if await CONTEXT.database.collections.get_by_name(request.name) is not None:
            raise HTTPException(
                status_code=409, detail=f"Collection '{request.name}' already exists."
            )

    # 3. Restore any masked provider secret BEFORE validating/storing: a caller that read a collection
    #    (secrets masked) and PATCHed a blob back sends the mask verbatim — that means "keep the stored
    #    key", never "set the key to the literal mask". Healed against the real stored blobs by node id.
    healed_pipeline = (
        restore_blob_secrets(request.pipeline, current.pipeline)
        if request.pipeline is not None
        else None
    )
    healed_search = (
        restore_blob_secrets(request.search, current.search) if request.search is not None else None
    )

    # 3a. A new pipeline never reaches storage broken: heal it to the current engine, validate it,
    #     and keep its stamped canonical form for storage (step 6).
    stored_pipeline = (
        CollectionHelpers.canonical_pipeline(healed_pipeline)
        if healed_pipeline is not None
        else None
    )

    # 3b. A new search blob is a search GRAPH blob: {} (stock default) is always allowed; a non-empty
    #     one is shape-guarded and validated as a genuine SEARCH pipeline before it can be stored.
    if healed_search is not None and healed_search != {}:
        CollectionHelpers.validate_search_blob(healed_search)

    # 3c. Validate the schema diff BEFORE any write — a bad field must 422 without having already
    #     committed the identity/limits rename (the writes below are not one transaction).
    if request.fields is not None:
        CollectionHelpers.validate_fields(request.fields)

    # 4. Identity/limits (no-op when untouched).
    if any(
        v is not None
        for v in (
            request.name,
            request.supported_formats,
            request.max_file_size_bytes,
            request.job_timeout_seconds,
        )
    ):
        await CONTEXT.database.collections.update_contract(
            collection_id,
            name=request.name,
            supported_formats=request.supported_formats,
            max_file_size_bytes=request.max_file_size_bytes,
            job_timeout_seconds=request.job_timeout_seconds,
        )

    # 5. Schema evolution by DIFF — existing metadata values survive untouched fields; a searchable
    #    change flips needs_reindex inside the facade, then the store is RECONCILED (not just flagged):
    #    a newly filterable field gets its Qdrant payload index added live and the backfills repopulate
    #    existing points; a newly semantic/lexical field needs a named vector Qdrant can't add live, so
    #    a reindex is required to make it searchable.
    if request.fields is not None:
        try:
            reindex = await CONTEXT.database.collections.update_schema(
                collection_id, CollectionHelpers.to_field_rows(request.fields)
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        await CollectionStoreSync.reconcile_and_backfill(collection_id)
        if reindex:
            CONTEXT.logger.warning(
                f"Collection {collection_id}: searchable schema changed — reindex required"
            )

    # 6. Config blobs (append an immutable version snapshot). The pipeline is stored in its stamped
    #    canonical form so subsequent runs/uploads fast-path. A pipeline edit that changes the EMBED
    #    vector space (different embedder model/provider, toggled sparse) flips needs_reindex
    #    — otherwise new documents would be embedded into a space incompatible with the stored ones,
    #    silently degrading search. None leaves the flag as-is (a schema change may already have set it).
    reindex_from_embed: bool | None = None
    if stored_pipeline is not None and CollectionHelpers.embed_space_changed(
        current.pipeline, stored_pipeline
    ):
        reindex_from_embed = True
        CONTEXT.logger.warning(
            f"Collection {collection_id}: embed vector space changed — reindex required"
        )
    if request.pipeline is not None or request.search is not None:
        await CONTEXT.database.collections.update_config(
            collection_id,
            pipeline=stored_pipeline,
            search=healed_search,
            needs_reindex=reindex_from_embed,
            note=request.note,
        )

    updated = await CONTEXT.database.collections.get(collection_id)
    return CollectionHelpers.to_model(
        updated, await CONTEXT.database.collections.get_schema(collection_id)
    )


@router.delete(
    "/{collection_id}",
    status_code=204,
    dependencies=[Depends(require(Capability.WRITE))],
)
@auto_handle_errors
async def delete_collection(collection_id: uuid.UUID) -> None:
    """
    Delete a collection (404 when unknown).
    """
    deleted = await CONTEXT.database.collections.delete(collection_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")
    CONTEXT.logger.info(f"Collection {collection_id} deleted")


__all__ = ["router"]
