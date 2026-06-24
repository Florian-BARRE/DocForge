# ====== Code Summary ======
# Collection configuration section — a sub-resource of a collection.
# Endpoints: state / schema / history (read), update / rollback (mutations).
# Every pipeline echoed back is credential-redacted.

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, HTTPException

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.utils.error_handling import auto_handle_errors
from backend.routers.collections.config.models import (
    ConfigHistoryResponse,
    ConfigRollbackRequest,
    ConfigSchemaResponse,
    ConfigStateResponse,
    ConfigUpdateRequest,
    ConfigVersionSummary,
)
from common_libs.config.validation import ConfigDocument, ConfigExplainer, ConfigValidator

router = APIRouter(tags=["config"])


# ─────────────────────────── Read ───────────────────────────


@router.get("/state", response_model=ConfigStateResponse)
@auto_handle_errors
async def get_config_state(collection_id: uuid.UUID) -> ConfigStateResponse:
    """Return the collection's complete current configuration (pipeline credentials redacted)."""
    # 1. Load the collection (with metadata fields)
    collection = await _load(collection_id)

    # 2. Build the redacted state payload
    return _state_response(collection)


@router.get("/schema", response_model=ConfigSchemaResponse)
@auto_handle_errors
async def get_config_schema(collection_id: uuid.UUID) -> ConfigSchemaResponse:
    """Return this collection's metadata schema: system (auto-extracted) + custom (caller-provided)."""
    # 1. Load the collection
    collection = await _load(collection_id)

    # 2. Return the metadata fields for this collection (system + custom, as stored)
    doc = ConfigDocument.from_collection(collection)
    return ConfigSchemaResponse(metadata_fields=doc["metadata_fields"])


@router.get("/history", response_model=ConfigHistoryResponse)
@auto_handle_errors
async def config_history(collection_id: uuid.UUID) -> ConfigHistoryResponse:
    """List the config version history (newest first)."""
    # 1. Existence check
    await _load(collection_id)

    # 2. Read the audit log
    async with CONTEXT.postgres.session() as session:
        versions = await CONTEXT.config_repo.list_versions(session, collection_id)

    return ConfigHistoryResponse(
        collection_id=str(collection_id),
        total=len(versions),
        versions=[
            ConfigVersionSummary(
                version=v.version, pipeline_version=v.pipeline_version,
                note=v.note, created_at=v.created_at,
            )
            for v in versions
        ],
    )


# ─────────────────────────── Mutations ───────────────────────────


@router.post("/update", response_model=ConfigStateResponse)
@auto_handle_errors
async def update_config(
    collection_id: uuid.UUID, body: ConfigUpdateRequest
) -> ConfigStateResponse:
    """
    Partially update the config (provided keys replace existing values).

    Validated before applying; on success the new config is snapshotted and the collection's
    pipeline_version is bumped if the pipeline or embedding model changed (the latter also flags
    the collection for reindex).
    """
    # 1. Merge patch onto current document
    collection = await _load(collection_id)
    merged = ConfigDocument.merge_patch(ConfigDocument.from_collection(collection), body.patch)

    # 2. Validate, then apply (transparency: what the caller actually sent in the patch)
    return await _validate_and_apply(
        collection_id, merged, note=body.note,
        provided_keys=set(body.patch.keys()),
        raw_pipeline=body.patch.get("pipeline"),
        submitted_field_names=[f.get("field_name") for f in body.patch.get("metadata_fields", []) if isinstance(f, dict)],
    )


@router.post("/rollback", response_model=ConfigStateResponse)
@auto_handle_errors
async def rollback_config(
    collection_id: uuid.UUID, body: ConfigRollbackRequest
) -> ConfigStateResponse:
    """
    Roll the config back to a previous version (re-applied as a new version).

    Rollback does not rewrite history: the chosen snapshot's config is re-validated and applied,
    producing a fresh history entry noted as a rollback.
    """
    # 1. Resolve the target snapshot
    await _load(collection_id)
    async with CONTEXT.postgres.session() as session:
        snapshot = await CONTEXT.config_repo.get_version(session, collection_id, body.version)
    if snapshot is None:
        # 404 — requested config version does not exist in this collection's history.
        CONTEXT.logger.warning(
            f"Config rollback rejected (404 unknown version): collection={collection_id} "
            f"version={body.version}"
        )
        raise HTTPException(
            status_code=404,
            detail=f"Config version {body.version} not found for collection {collection_id}.",
        )

    # 2. Validate the snapshot's config, then apply it as a new version (the whole doc is "provided")
    snapshot_doc = dict(snapshot.config)
    return await _validate_and_apply(
        collection_id, snapshot_doc, note=f"rollback to v{body.version}",
        provided_keys=set(snapshot_doc.keys()),
        raw_pipeline=snapshot_doc.get("pipeline"),
        submitted_field_names=[f.get("field_name") for f in snapshot_doc.get("metadata_fields", []) if isinstance(f, dict)],
    )


# ─────────────────────────── Private helpers ───────────────────────────


async def _load(collection_id: uuid.UUID):
    """Load a collection (with metadata_fields) or raise 404."""
    async with CONTEXT.postgres.session() as session:
        collection = await CONTEXT.collection_repo.get_by_id(session, collection_id)
    if collection is None:
        # 404 — config sub-resource requested for a collection that does not exist.
        CONTEXT.logger.warning(f"Config request rejected (404 unknown collection): collection={collection_id}")
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")
    return collection


async def _validate_and_apply(
    collection_id: uuid.UUID,
    doc: dict[str, Any],
    *,
    note: str | None,
    provided_keys: set[str],
    raw_pipeline: dict[str, Any] | None,
    submitted_field_names: list[str] | None = None,
) -> ConfigStateResponse:
    """
    Resolve defaults, validate, and apply a config document; return the transparent state.

    Args:
        collection_id (uuid.UUID): Target collection.
        doc (dict): The full canonical config document to apply.
        note (str | None): Change note recorded in the version history.
        provided_keys (set[str]): Top-level keys the caller actually supplied (for transparency).
        raw_pipeline (dict | None): The pipeline as sent by the caller (pre-defaults).
        submitted_field_names (list[str] | None): Field names the caller submitted (override detection).

    Returns:
        ConfigStateResponse: The new (redacted) config state + the `applied` transparency envelope.

    Raises:
        HTTPException: 422 when the config has any error-severity issue.
    """
    # 1. Fill pipeline defaults so the stored/echoed config is complete and self-describing
    doc = ConfigDocument.resolve_pipeline(doc)

    # 2. Run the coherence validator; block on any error-severity issue
    issues = ConfigValidator.validate(doc, CONTEXT.registry.describe_stages()["stages"])
    errors = [i for i in issues if i["severity"] == "error"]
    if errors:
        # 422 — the resolved config has at least one error-severity coherence issue.
        CONTEXT.logger.warning(
            f"Config apply rejected (422 invalid config): collection={collection_id} "
            f"provided_keys={sorted(provided_keys)} errors={errors}"
        )
        raise HTTPException(status_code=422, detail={"message": "Invalid configuration.", "issues": issues})

    # 3. Apply + snapshot
    async with CONTEXT.postgres.session() as session:
        collection = await CONTEXT.config_repo.apply_config(session, collection_id, doc, note=note)
    if collection is None:
        # 404 — collection was deleted between the existence check and apply.
        CONTEXT.logger.warning(
            f"Config apply rejected (404 unknown collection): collection={collection_id}"
        )
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")

    # Mutation succeeded — record the new pipeline version + whether a reindex is now required.
    CONTEXT.logger.info(
        f"Config applied collection={collection_id} note={note!r} "
        f"pipeline_version={collection.pipeline_version} needs_reindex={collection.needs_reindex}"
    )

    # 4. Build the transparency envelope from the applied result
    applied = ConfigExplainer.build(
        provided_keys=provided_keys,
        raw_pipeline=raw_pipeline,
        resolved_doc=ConfigDocument.from_collection(collection),
        issues=issues,
        needs_reindex=collection.needs_reindex,
        reindex_reasons=list(getattr(collection, "_reindex_reasons", []) or []),
        custom_field_names=submitted_field_names,
    )
    return ConfigStateResponse.from_collection(collection, applied=applied)


def _state_response(collection: Any) -> ConfigStateResponse:
    """Build the redacted ConfigStateResponse from a CollectionModel (no caller action → no `applied`)."""
    return ConfigStateResponse.from_collection(collection)
