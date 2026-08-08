# ====== Code Summary ======
# Pydantic models for the collections router — the contract the UI creates and edits:
# identity + limits, the FULL metadata schema (declared up front: named vectors cannot be
# added to Qdrant later), and the two config blobs (pipeline graph + search).

# ====== Standard Library Imports ======
from datetime import datetime
from typing import Any, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldOrigin, FieldScope, FieldType


class FieldSpecModel(BaseModel):
    """One metadata field of the collection's contract (declared OR generated)."""

    # A typo in a field flag (filterable/lexical/semantic) must FAIL, never be silently dropped —
    # a swallowed flag would build the wrong vector space. Mirrors the pipeline's extra="forbid".
    model_config = ConfigDict(extra="forbid")

    field_name: str = Field(description="Unique field name within the collection.")
    field_type: FieldType = Field(description="Value type — drives validation and storage.")
    required: bool = Field(default=False, description="Upload refused without it (user fields).")
    filterable: bool = Field(default=False, description="Present in the Qdrant payload (lean).")
    lexical: bool = Field(default=False, description="Gets a sparse BM25 named vector.")
    semantic: bool = Field(default=False, description="Gets a dense named vector.")
    enum_values: list[str] | None = Field(
        default=None, description="Allowed values when field_type is enum."
    )
    origin: FieldOrigin = Field(
        default=FieldOrigin.USER, description="user (declared at upload) or generated (metagen)."
    )
    scope: FieldScope = Field(
        default=FieldScope.DOCUMENT, description="document or chunk level value."
    )


class CollectionModel(BaseModel):
    """One collection — the full contract the UI displays and edits."""

    id: str = Field(description="The collection's UUID.")
    name: str = Field(description="Unique human name.")
    supported_formats: list[str] = Field(description="Accepted upload extensions (e.g. pdf).")
    max_file_size_bytes: int = Field(description="Upload size ceiling, bytes.")
    job_timeout_seconds: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Per-collection whole-ingest-job wall-clock budget, seconds. None = inherit the "
            "worker's global WORKER_JOB_TIMEOUT_SECONDS default."
        ),
    )
    needs_reindex: bool = Field(description="True when a config change requires reindexing.")
    created_at: datetime | None = Field(default=None, description="Creation timestamp.")
    pipeline: dict[str, Any] = Field(description="The ingestion pipeline blob (the graph).")
    search: dict[str, Any] = Field(
        description="The search pipeline graph blob ({} = use the stock default)."
    )
    fields: list[FieldSpecModel] = Field(default_factory=list, description="The metadata schema.")


class CollectionContractModel(BaseModel):
    """
    The editable IDENTITY + LIMITS contract of a collection — the scalar/enum fields ONLY.

    This is the ONE source of truth for the identity/limits shape: ``CreateCollectionRequest``
    composes it (so the request and the schema can never drift), and its ``model_json_schema()``
    is served on the discovery surface so a schema-driven UI renders the form with zero hardcoded
    field knowledge — exactly like a node's ``config_schema``. It deliberately excludes ``fields``
    (the metadata schema) and the ``pipeline`` / ``search`` graph blobs, which have their own
    dedicated editors.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Unique human name.")
    supported_formats: list[str] = Field(description="Accepted upload extensions (e.g. pdf).")
    max_file_size_bytes: int = Field(description="Upload size ceiling, bytes.")
    job_timeout_seconds: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Per-collection whole-ingest-job wall-clock budget, seconds. None (default) = inherit "
            "the worker's global WORKER_JOB_TIMEOUT_SECONDS."
        ),
    )
    preset: Literal["standard", "light"] | None = Field(
        default=None,
        description=(
            "Stock-blob selector used ONLY when ``pipeline`` is omitted: 'standard' (the default "
            "full pipeline) or 'light' (a fast, local, free core — no figure enrich, contextualise "
            "or metagen). An explicit ``pipeline`` always wins over this."
        ),
    )


class CreateCollectionRequest(CollectionContractModel):
    """Create a collection from A to Z — the identity/limits contract, schema and (optionally) its pipeline."""

    fields: list[FieldSpecModel] = Field(
        default_factory=list,
        description="The FULL schema, declared up front (vector space is fixed at creation).",
    )
    pipeline: dict[str, Any] | None = Field(
        default=None,
        description="The pipeline blob; omitted → the stock blob selected by ``preset``.",
    )


class UpdateCollectionRequest(BaseModel):
    """
    Patch any part of the collection — identity/limits, metadata schema, config blobs.

    Schema updates are applied by DIFF (existing values survive untouched fields); a change
    to the SEARCHABLE surface flips needs_reindex. Config changes append immutable versions.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, description="New unique name.")
    supported_formats: list[str] | None = Field(
        default=None, description="New accepted upload extensions."
    )
    max_file_size_bytes: int | None = Field(default=None, description="New size ceiling, bytes.")
    job_timeout_seconds: float | None = Field(
        default=None,
        gt=0,
        description=(
            "New per-collection whole-ingest-job wall-clock budget, seconds. Omitted = leave the "
            "current value unchanged; a set value overrides the global WORKER_JOB_TIMEOUT_SECONDS."
        ),
    )
    fields: list[FieldSpecModel] | None = Field(
        default=None,
        description="The TARGET schema (diffed by field name; omitted fields are removed).",
    )
    pipeline: dict[str, Any] | None = Field(
        default=None, description="New pipeline blob (validated before being stored)."
    )
    search: dict[str, Any] | None = Field(
        default=None,
        description="New search pipeline graph blob ({} = stock default; validated before storage).",
    )
    note: str | None = Field(default=None, description="Version note shown in the history.")


class CollectionContractSchemaResponse(BaseModel):
    """
    The JSON Schema of the collection identity/limits contract — the discovery payload.

    Mirrors a node's ``config_schema`` face: ``config_schema`` is the raw
    ``CollectionContractModel.model_json_schema()`` the frontend hands to its existing
    ``SchemaForm`` unchanged, so a new scalar contract field auto-surfaces in the UI with zero
    frontend change.

    Attributes:
        config_schema (dict[str, Any]): JSON Schema of the editable identity/limits contract.
    """

    config_schema: dict[str, Any] = Field(
        description="JSON Schema of the collection identity/limits contract (drives the UI form)."
    )


__all__ = [
    "FieldSpecModel",
    "CollectionModel",
    "CollectionContractModel",
    "CollectionContractSchemaResponse",
    "CreateCollectionRequest",
    "UpdateCollectionRequest",
]
