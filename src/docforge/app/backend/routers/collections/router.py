# ====== Code Summary ======
# The collections router — the contract's CRUD: create (schema declared up front + pipeline
# blob seeded with the product default), read, patch the config blobs (pipeline VALIDATED
# before storage — a broken graph never reaches the worker), delete. Every rejection carries
# an explicit HTTP code and a precise message.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException

# ====== Internal Project Imports ======
from shared_libs.pipelines.ingest import (
    BlobNormalizationError,
    BlobNormalizer,
    IngestPipeline,
)
from shared_libs.public_models import FieldOrigin, FieldScope
from shared_libs.services.db.postgresql.tables import Collection, MetadataField
from shared_libs.services.db.qdrant import RESERVED_PAYLOAD_KEYS

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import AuthPrincipal, Capability, KeyPermissions, require
from ...utils.error_handling import auto_handle_errors
from ...utils.pipeline_validation import PipelineBlobValidator
from ...utils.search_blob_validation import SearchBlobValidator
from .models import (
    CollectionModel,
    CreateCollectionRequest,
    FieldSpecModel,
    UpdateCollectionRequest,
)
from .redaction import redact_blob_secrets, restore_blob_secrets

router = APIRouter(prefix="/collections", tags=["collections"])


def _public_pipeline(pipeline: dict | None) -> dict | None:
    """Strip the internal version stamp so the API exposes a clean, editable graph blob.

    The stamp is a STORAGE-side optimization (fast-path detection); the ``GroupNodeBlob`` the UI
    posts back to the stage endpoints forbids extra keys, so it must never see the reserved key.
    """
    if not isinstance(pipeline, dict):
        return pipeline
    return {key: value for key, value in pipeline.items() if key != BlobNormalizer.STAMP_KEY}


def _to_model(collection: Collection, fields: list[MetadataField]) -> CollectionModel:
    """Map the rows to the UI contract (shared by every read path).

    Provider secrets (api_key on every provider node of the pipeline AND search blobs) are masked
    here — the ONE serialisation boundary every read path funnels through — so a live key is never
    echoed to a client. The stored blobs keep the real keys; only this outbound copy is masked.
    """
    return CollectionModel(
        id=str(collection.id),
        name=collection.name,
        supported_formats=list(collection.supported_formats),
        max_file_size_bytes=collection.max_file_size_bytes,
        needs_reindex=collection.needs_reindex,
        created_at=collection.created_at,
        pipeline=redact_blob_secrets(_public_pipeline(collection.pipeline)),
        search=redact_blob_secrets(collection.search),
        fields=[
            FieldSpecModel(
                field_name=row.field_name,
                field_type=row.field_type,
                required=row.required,
                filterable=row.filterable,
                lexical=row.lexical,
                semantic=row.semantic,
                enum_values=row.enum_values,
                origin=row.origin,
                scope=row.scope,
            )
            for row in fields
        ],
    )


# Payload keys the chunk point owns for its own machinery (id, ordinal, enable-filter). A
# filterable field is denormalised onto the point by NAME, so a field sharing one of these would
# overwrite it and corrupt search/deletion — reserved regardless of the current filterable flag,
# which can be toggled on later.
# "content" is the search-target sentinel for the chunk body; a metadata field of that name would
# be un-targetable (it always resolves to the body vectors), so it is reserved alongside the
# point's own payload keys (RESERVED_PAYLOAD_KEYS — the single source, shared with the writers).
_RESERVED_FIELD_NAMES = RESERVED_PAYLOAD_KEYS | {"content"}


def _validate_fields(fields: list[FieldSpecModel]) -> None:
    """Schema-level guards with explicit 422s (mirror of the DB CHECK constraints)."""
    for spec in fields:
        # Chunk-scope values are produced by the pipeline — a user cannot declare them
        # at upload, so chunk scope is reserved for GENERATED fields (DB CHECK mirrors this).
        if spec.scope == FieldScope.CHUNK and spec.origin != FieldOrigin.GENERATED:
            raise HTTPException(
                status_code=422,
                detail=f"Field '{spec.field_name}': chunk scope is reserved for generated "
                f"fields — user-declared metadata is document-level.",
            )
        # A field name must never shadow a reserved chunk-payload key (it would overwrite it
        # when denormalised onto the point, breaking the enabled-filter or deletion-by-document).
        if spec.field_name in _RESERVED_FIELD_NAMES:
            raise HTTPException(
                status_code=422,
                detail=f"Field name '{spec.field_name}' is reserved — pick another name "
                f"(reserved: {sorted(_RESERVED_FIELD_NAMES)}).",
            )
        # Chunk-scope lexical has no producer: the embed node writes chunk-scope SEMANTIC (dense)
        # vectors and the meta-vector facade is document-scope only, so a chunk-scope lexical field
        # would declare a meta_<slug>_bm25 vector nothing ever fills — a silent-empty search. Reject
        # it up front rather than accept a config that can never return results.
        if spec.scope == FieldScope.CHUNK and spec.lexical:
            raise HTTPException(
                status_code=422,
                detail=f"Field '{spec.field_name}': chunk-scope lexical search is not supported "
                f"(no BM25 producer for chunk metadata) — use semantic, or document scope.",
            )


def _canonical_pipeline(blob: dict) -> dict:
    """Heal a pipeline blob to the current engine, validate it, and return its stored form.

    The stored form is normalized (auto-migrated to the current-engine topology) and version-stamped,
    so a freshly written blob is already canonical and every subsequent run/upload fast-paths. A blob
    that cannot be migrated is a 422 with the explicit recovery, mirroring the structural validator.

    Args:
        blob (dict): The caller's (or default) pipeline blob.

    Returns:
        dict: The normalized, version-stamped blob to persist.

    Raises:
        HTTPException: 422 when the blob cannot be migrated or fails structural validation.
    """
    # 1. Auto-heal to the current-engine topology (a stale/unrecognisable blob is a clear 422).
    try:
        canonical = BlobNormalizer.normalize(blob)
    except BlobNormalizationError as exc:
        raise HTTPException(status_code=422, detail=f"Pipeline blob cannot be migrated: {exc}")

    # 2. Structural validation runs on the healed, stamp-free shape (the builder forbids extras).
    PipelineBlobValidator.validate(canonical)

    # 3. Persist the stamped canonical form so future reads fast-path.
    return BlobNormalizer.stamp(canonical)


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
    return [_to_model(c, await CONTEXT.database.collections.get_schema(c.id)) for c in collections]


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
    return _to_model(collection, await CONTEXT.database.collections.get_schema(collection_id))


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

    _validate_fields(request.fields)

    # 2. The pipeline blob: the caller's, or the product default — healed to the current engine,
    #    validated, and stamped for storage either way.
    blob = _canonical_pipeline(
        request.pipeline or IngestPipeline.default_blob().model_dump(mode="json")
    )

    # 3. Create contract + schema in one transaction (slug collisions → explicit 422).
    rows = [
        MetadataField(
            field_name=f.field_name,
            field_type=f.field_type,
            required=f.required,
            filterable=f.filterable,
            lexical=f.lexical,
            semantic=f.semantic,
            enum_values=f.enum_values,
            origin=f.origin,
            scope=f.scope,
        )
        for f in request.fields
    ]
    try:
        created = await CONTEXT.database.collections.create(
            Collection(
                name=request.name,
                supported_formats=request.supported_formats,
                max_file_size_bytes=request.max_file_size_bytes,
                pipeline=blob,
                search={},
            ),
            rows,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # 4. Ownership: a scoped, list-scoped key that just created this collection is granted access to
    #    it by appending the id to its own scope (root / wildcard keys already cover everything).
    await _grant_creator_scope(principal, str(created.id))

    CONTEXT.logger.info(f"Collection '{request.name}' created ({len(rows)} fields)")
    return _to_model(created, await CONTEXT.database.collections.get_schema(created.id))


async def _grant_creator_scope(principal: AuthPrincipal, collection_id: str) -> None:
    """
    Append a freshly created collection's id to the creating key's own scope.

    No-op for the full-access principal (auth off / root key) and for wildcard-scoped keys, which
    already cover every collection. Only a list-scoped key needs (and gets) the new id.

    Args:
        principal (AuthPrincipal): The authenticated creator.
        collection_id (str): The new collection's id to bring into the key's scope.
    """
    key = principal.key
    if principal.is_full_access or key is None or key.permissions is None:
        return
    scope = KeyPermissions.model_validate(key.permissions)
    if "*" in scope.collections or collection_id in scope.collections:
        return
    scope.collections.append(collection_id)
    await CONTEXT.database.auth.update_key_permissions(key.id, scope.model_dump(mode="json"))


# The embed-node config keys that define the vector space (a change to any means already-stored
# vectors were produced by a different/incompatible embedder → the collection must be reindexed).
_EMBED_VECTOR_KEYS = ("base_url", "model", "embed_sparse", "embed_semantic_fields")


def _embed_vector_space(blob: dict) -> list:
    """A stable fingerprint of every embed node's vector-space-affecting config in a pipeline blob.

    Two blobs with the same fingerprint produce vectors in the same space; a difference means a
    reindex is required (e.g. a swapped embed model/provider, toggled sparse).
    """
    fingerprint: list = []

    def walk(nodes: list) -> None:
        for node in nodes:
            if node.get("family") == "embed":
                config = node.get("config") or {}
                fingerprint.append(
                    (
                        node.get("id"),
                        node.get("kind"),
                        tuple((key, config.get(key)) for key in _EMBED_VECTOR_KEYS),
                    )
                )
            body = node.get("body")
            if isinstance(body, dict):
                walk(body.get("nodes") or [])

    walk(blob.get("nodes") or [])
    return sorted(fingerprint)


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
    #    and keep its stamped canonical form for storage (step 6).
    stored_pipeline = _canonical_pipeline(healed_pipeline) if healed_pipeline is not None else None

    # 3b. A new search blob is a search GRAPH blob. Only two shapes are valid: {} (the sentinel
    #     "use the stock default", always allowed) or a real topology carrying a "nodes" list. A
    #     non-empty dict WITHOUT "nodes" would be stored then silently ignored at read (__resolve_blob
    #     falls back to the default) — reject it up front. A real topology is validated not just
    #     structurally but as a genuine SEARCH pipeline (it must terminate on a SearchResult), so a
    #     non-search graph cannot be stored to 500 on every subsequent query.
    if healed_search is not None and healed_search != {}:
        if "nodes" not in healed_search:
            raise HTTPException(
                status_code=422,
                detail="collection.search must be empty ({} = stock default) or a search graph "
                "blob with a 'nodes' list.",
            )
        SearchBlobValidator.validate(healed_search)

    # 3c. Validate the schema diff BEFORE any write — a bad field must 422 without having already
    #     committed the identity/limits rename (the writes below are not one transaction).
    if request.fields is not None:
        _validate_fields(request.fields)

    # 4. Identity/limits (no-op when untouched).
    if any(
        v is not None
        for v in (request.name, request.supported_formats, request.max_file_size_bytes)
    ):
        await CONTEXT.database.collections.update_contract(
            collection_id,
            name=request.name,
            supported_formats=request.supported_formats,
            max_file_size_bytes=request.max_file_size_bytes,
        )

    # 5. Schema evolution by DIFF — existing metadata values survive untouched fields;
    #    a searchable-surface change flips needs_reindex inside the facade.
    if request.fields is not None:
        rows = [
            MetadataField(
                field_name=f.field_name,
                field_type=f.field_type,
                required=f.required,
                filterable=f.filterable,
                lexical=f.lexical,
                semantic=f.semantic,
                enum_values=f.enum_values,
                origin=f.origin,
                scope=f.scope,
            )
            for f in request.fields
        ]
        try:
            reindex = await CONTEXT.database.collections.update_schema(collection_id, rows)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
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
    if stored_pipeline is not None and _embed_vector_space(current.pipeline) != _embed_vector_space(
        stored_pipeline
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
    return _to_model(updated, await CONTEXT.database.collections.get_schema(collection_id))


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
