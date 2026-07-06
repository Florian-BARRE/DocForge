# ====== Code Summary ======
# The collections router — the contract's CRUD: create (schema declared up front + pipeline
# blob seeded with the product default), read, patch the config blobs (pipeline VALIDATED
# before storage — a broken graph never reaches the worker), delete. Every rejection carries
# an explicit HTTP code and a precise message.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, HTTPException

# ====== Internal Project Imports ======
from shared_libs.pipelines.build import BuildError
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.public_models import FieldOrigin, FieldScope
from shared_libs.services.db.postgresql.tables import Collection, MetadataField

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...utils.error_handling import auto_handle_errors
from .models import (
    CollectionModel,
    CreateCollectionRequest,
    FieldSpecModel,
    UpdateCollectionRequest,
)

router = APIRouter(prefix="/collections", tags=["collections"])


def _to_model(collection: Collection, fields: list[MetadataField]) -> CollectionModel:
    """Map the rows to the UI contract (shared by every read path)."""
    return CollectionModel(
        id=str(collection.id),
        name=collection.name,
        supported_formats=list(collection.supported_formats),
        max_file_size_bytes=collection.max_file_size_bytes,
        needs_reindex=collection.needs_reindex,
        created_at=collection.created_at,
        pipeline=collection.pipeline,
        search=collection.search,
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


def _validate_pipeline(blob: dict) -> None:
    """Build + validate a pipeline blob — 422 with every issue when broken."""
    try:
        group = CONTEXT.pipeline_builder.build(blob)
    except BuildError as exc:
        raise HTTPException(status_code=422, detail=f"Pipeline blob cannot be built: {exc}")
    issues = CONTEXT.graph_validator.validate(group)
    if issues:
        raise HTTPException(
            status_code=422,
            detail=[
                {"code": issue.code.value, "location": issue.location, "message": issue.message}
                for issue in issues
            ],
        )


@router.get("", response_model=list[CollectionModel])
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
        _to_model(c, await CONTEXT.database.collections.get_schema(c.id)) for c in collections
    ]


@router.get("/{collection_id}", response_model=CollectionModel)
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


@router.post("", response_model=CollectionModel, status_code=201)
@auto_handle_errors
async def create_collection(request: CreateCollectionRequest) -> CollectionModel:
    """
    Create a collection from A to Z — contract + full schema + pipeline blob.

    Returns:
        CollectionModel: The created contract (201); 409 on name clash, 422 on bad
        pipeline or colliding vector slugs.
    """
    # 1. Name unicity — explicit 409, not a driver error.
    if await CONTEXT.database.collections.get_by_name(request.name) is not None:
        raise HTTPException(status_code=409, detail=f"Collection '{request.name}' already exists.")

    _validate_fields(request.fields)

    # 2. The pipeline blob: the caller's, or the product default — validated either way.
    blob = request.pipeline or IngestPipeline.default_blob().model_dump(mode="json")
    _validate_pipeline(blob)

    # 3. Create contract + schema in one transaction (slug collisions → explicit 422).
    rows = [
        MetadataField(
            field_name=f.field_name, field_type=f.field_type, required=f.required,
            filterable=f.filterable, lexical=f.lexical, semantic=f.semantic,
            enum_values=f.enum_values, origin=f.origin, scope=f.scope,
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
    CONTEXT.logger.info(f"Collection '{request.name}' created ({len(rows)} fields)")
    return _to_model(created, await CONTEXT.database.collections.get_schema(created.id))


@router.patch("/{collection_id}", response_model=CollectionModel)
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

    # 3. A new pipeline never reaches storage broken.
    if request.pipeline is not None:
        _validate_pipeline(request.pipeline)

    # 4. Identity/limits (no-op when untouched).
    if any(v is not None for v in (request.name, request.supported_formats,
                                   request.max_file_size_bytes)):
        await CONTEXT.database.collections.update_contract(
            collection_id,
            name=request.name,
            supported_formats=request.supported_formats,
            max_file_size_bytes=request.max_file_size_bytes,
        )

    # 5. Schema evolution by DIFF — existing metadata values survive untouched fields;
    #    a searchable-surface change flips needs_reindex inside the facade.
    if request.fields is not None:
        _validate_fields(request.fields)
        rows = [
            MetadataField(
                field_name=f.field_name, field_type=f.field_type, required=f.required,
                filterable=f.filterable, lexical=f.lexical, semantic=f.semantic,
                enum_values=f.enum_values, origin=f.origin, scope=f.scope,
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

    # 6. Config blobs (append an immutable version snapshot).
    if request.pipeline is not None or request.search is not None:
        await CONTEXT.database.collections.update_config(
            collection_id,
            pipeline=request.pipeline,
            search=request.search,
            note=request.note,
        )

    updated = await CONTEXT.database.collections.get(collection_id)
    return _to_model(updated, await CONTEXT.database.collections.get_schema(collection_id))


@router.delete("/{collection_id}", status_code=204)
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
