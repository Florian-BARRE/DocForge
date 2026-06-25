# ====== Code Summary ======
# Collections section: list / create / delete.
# - create: server injects the system metadata fields (client sends only custom), rejects a
#   duplicate name with 409, persists the contract + merged schema.
# - delete: drops the Qdrant collection + Postgres rows, and deletes S3 blobs EXCEPT those
#   still referenced by another collection (content-addressed sharing).

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.auth import Principal, require_collection_role, require_principal
from backend.libs.utils.error_handling import auto_handle_errors
from backend.routers.collections.config.models import ConfigStateResponse
from backend.routers.collections.models import (
    CollectionListResponse,
    CollectionResponse,
    CreateCollectionRequest,
    DeleteResponse,
)
from common_libs.config.validation import ConfigDocument, ConfigExplainer, ConfigValidator
from common_libs.storage.postgres.models import GrantRole
from common_libs.storage.s3.helpers import S3Helpers

router = APIRouter(tags=["collections"])


@router.get("/list", response_model=CollectionListResponse)
@auto_handle_errors
async def list_collections(
    principal: Principal = Depends(require_principal),
) -> CollectionListResponse:
    """
    List collections visible to the caller (newest first).

    Root sees every collection; a standard user sees only the collections they hold any grant on
    (per-collection authorization model). The list is filtered server-side so a user can never
    enumerate collections they have no access to.
    """
    # 1. Read all collections, then scope to what the caller may see
    async with CONTEXT.postgres.session() as session:
        collections = await CONTEXT.collection_repo.list_all(session)
        if not principal.is_root:
            # Standard user — keep only collections they have a grant on.
            allowed = set(
                await CONTEXT.grant_repo.list_collection_ids_for_user(
                    session, principal.user_id
                )
            )
            collections = [c for c in collections if c.id in allowed]

    return CollectionListResponse(
        collections=[CollectionResponse.model_validate(c) for c in collections],
        total=len(collections),
    )


@router.post("/create", response_model=ConfigStateResponse, status_code=201)
@auto_handle_errors
async def create_collection(
    body: CreateCollectionRequest, principal: Principal = Depends(require_principal)
) -> ConfigStateResponse:
    """
    Create a collection.  The system metadata fields are always injected server-side; the client
    only sends custom business fields (and may override a system field's search flags).  The
    pipeline may be supplied fully, partially, or omitted — omitted/partial knobs are filled from
    defaults and the **resolved** config is persisted and echoed.

    The response is the full resolved config plus an ``applied`` transparency envelope detailing
    what the caller provided, what was defaulted, the system fields injected, and any warnings —
    so creation is fully self-explanatory.  A misconfigured pipeline raises 422 with the issues.
    """
    # 1. Merge metadata schema (system + custom) and resolve the pipeline defaults
    metadata_fields = ConfigDocument.merge_metadata_schema(body.metadata_schema)
    config_doc = ConfigDocument.resolve_pipeline({
        "supported_formats": list(body.supported_formats),
        "max_file_size_bytes": body.max_file_size_bytes,
        "locality_policy": body.locality_policy,
        "embedding_model": body.embedding_model,
        "unknown_field_policy": body.unknown_field_policy,
        "pipeline": dict(body.pipeline),
        "metadata_fields": metadata_fields,
    })

    # 2. Validate the resolved pipeline against the deployment's live stage schema before persisting
    issues = ConfigValidator.validate(config_doc, CONTEXT.registry.describe_stages()["stages"])
    errors = [i for i in issues if i["severity"] == "error"]
    if errors:
        # 422 — the requested pipeline config has at least one error-severity coherence issue.
        CONTEXT.logger.warning(
            f"Collection create rejected (422 invalid pipeline): name={body.name!r} errors={errors}"
        )
        raise HTTPException(
            status_code=422,
            detail={"message": "Invalid pipeline configuration.", "issues": issues},
        )

    # 3. Persist the RESOLVED config (defaults filled); a duplicate name → 409
    try:
        async with CONTEXT.postgres.session() as session:
            collection = await CONTEXT.collection_repo.create(
                session,
                name=body.name,
                supported_formats=body.supported_formats,
                max_file_size_bytes=body.max_file_size_bytes,
                locality_policy=body.locality_policy,
                embedding_model=body.embedding_model,
                unknown_field_policy=body.unknown_field_policy,
                pipeline=config_doc["pipeline"],
                metadata_fields=metadata_fields,
            )
    except IntegrityError:
        # 409 — a collection with this (unique) name already exists.
        CONTEXT.logger.warning(f"Collection create rejected (409 duplicate name): name={body.name!r}")
        raise HTTPException(status_code=409, detail=f"A collection named {body.name!r} already exists.")

    # 3b. Creator gets an admin grant on the new collection (GitHub-style ownership). Skipped for
    # root, which is implicitly admin on every collection — recording a grant would be redundant.
    if not principal.is_root:
        async with CONTEXT.postgres.session() as session:
            await CONTEXT.grant_repo.upsert(
                session,
                user_id=principal.user_id,
                collection_id=collection.id,
                role=GrantRole.ADMIN.value,
                granted_by=principal.user_id,
            )
        CONTEXT.logger.info(
            f"Granted creator admin on new collection id={collection.id} user_id={principal.user_id}"
        )

    # 4. Build the transparency envelope: what was provided vs defaulted at creation
    applied = ConfigExplainer.build(
        provided_keys=body.model_fields_set,
        raw_pipeline=body.pipeline,
        resolved_doc=ConfigDocument.from_collection(collection),
        issues=issues,
        needs_reindex=collection.needs_reindex,
        custom_field_names=[f.field_name for f in body.metadata_schema],
    )
    CONTEXT.logger.info(f"Created collection id={collection.id} name={body.name!r}")
    return ConfigStateResponse.from_collection(collection, applied=applied)


@router.delete(
    "/{collection_id}/delete",
    response_model=DeleteResponse,
    dependencies=[Depends(require_collection_role(GrantRole.ADMIN))],
)
@auto_handle_errors
async def delete_collection(collection_id: uuid.UUID) -> DeleteResponse:
    """
    Delete a collection and all associated data.

    Removes the Qdrant collection + Postgres rows (cascade), then deletes S3 blobs for every
    source_hash unique to this collection — blobs still referenced by another collection
    (content-addressed dedup) are left intact.
    """
    # 1. Resolve collection
    async with CONTEXT.postgres.session() as session:
        collection = await CONTEXT.collection_repo.get_by_id(session, collection_id)
    if collection is None:
        # 404 — cannot delete a collection that does not exist.
        CONTEXT.logger.warning(f"Collection delete rejected (404 unknown collection): collection={collection_id}")
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")

    # 2. Determine which blobs are safe to delete (not shared with other collections)
    async with CONTEXT.postgres.session() as session:
        source_hashes = await CONTEXT.document_repo.list_source_hashes(session, collection_id)
        deletable, kept = [], 0
        for sh in source_hashes:
            if await CONTEXT.document_repo.is_source_hash_shared(session, sh, collection_id):
                kept += 1
            else:
                deletable.append(sh)

    # 3. Drop the Qdrant collection (named by collection id) BEFORE the authoritative delete so a
    #    success leaves no orphan vectors. Best-effort by design: external-store cleanup must NEVER
    #    abort the Postgres delete (a flaky/unreachable Qdrant previously left the collection stuck,
    #    deletable only after the store recovered). drop_collection is already idempotent when the
    #    collection was never created (no ingest reached S6).
    if CONTEXT.qdrant is not None:
        try:
            await CONTEXT.qdrant.drop_collection(str(collection_id))
        except Exception as exc:  # noqa: BLE001 — cleanup failure must not block the delete
            CONTEXT.logger.warning(
                f"Qdrant drop failed for collection {collection_id} (continuing with delete): {exc}"
            )

    # 4. Delete the authoritative Postgres rows (cascade documents/blocks/chunks/jobs/metadata_field
    #    + stage_runs + collection_grant). This is THE step that makes the collection truly gone, so
    #    it runs even if the external-store cleanup above hiccupped. If it fails, the route errors
    #    (500 via @auto_handle_errors) and nothing is half-removed from the source of truth.
    async with CONTEXT.postgres.session() as session:
        await CONTEXT.collection_repo.delete(session, collection_id)

    # 5. Delete S3 blobs for non-shared source_hashes (best-effort, per-blob). The collection is
    #    already gone from the source of truth; content-addressed blob residue is harmless and
    #    dedup-safe, so a single flaky blob must not resurface the (now-deleted) collection.
    blobs_deleted = 0
    for sh in deletable:
        try:
            await CONTEXT.s3.delete(S3Helpers.key_original(sh))
            blobs_deleted += 1 + await CONTEXT.s3.delete_prefix(f"derived/{sh}/")
        except Exception as exc:  # noqa: BLE001 — cleanup failure must not block the delete
            CONTEXT.logger.warning(
                f"S3 cleanup failed for source_hash {sh} (continuing): {exc}"
            )

    CONTEXT.logger.info(
        f"Deleted collection {collection_id} (blobs_deleted={blobs_deleted}, blobs_kept_shared={kept})"
    )
    return DeleteResponse(deleted=True, id=collection_id)
