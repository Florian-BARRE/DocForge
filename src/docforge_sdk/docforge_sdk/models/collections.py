# ====== Code Summary ======
# Request/response models for the collections resource, mirrored field-for-field from the DocForge
# backend router models. The pipeline (ingest graph) and search blobs are opaque server-shaped JSON,
# so they are typed as plain dicts rather than the engine's structured blob models.

# ====== Standard Library Imports ======
from datetime import datetime
from typing import Any, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from ._shared import FieldOrigin, FieldScope, FieldType


class FieldSpec(BaseModel):
    """
    One metadata field of the collection's contract (declared OR generated).

    Attributes:
        field_name (str): Unique field name within the collection.
        field_type (FieldType): Value type — drives validation and storage.
        required (bool): Upload refused without it (user fields).
        filterable (bool): Present in the Qdrant payload (lean vector).
        lexical (bool): Gets a sparse BM25 named vector.
        semantic (bool): Gets a dense named vector.
        enum_values (list[str] | None): Allowed values when ``field_type`` is enum.
        origin (FieldOrigin): user (declared at upload) or generated (metagen).
        scope (FieldScope): document or chunk level value.
    """

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
    """
    One collection — the full contract the UI displays and edits.

    Attributes:
        id (str): The collection's UUID.
        name (str): Unique human name.
        supported_formats (list[str]): Accepted upload extensions (e.g. pdf).
        max_file_size_bytes (int): Upload size ceiling, bytes.
        job_timeout_seconds (float | None): Per-collection whole-ingest-job wall-clock budget,
            seconds. None = inherit the worker's global WORKER_JOB_TIMEOUT_SECONDS default.
        needs_reindex (bool): True when a config change requires reindexing.
        created_at (datetime | None): Creation timestamp.
        pipeline (dict[str, Any]): The ingestion pipeline blob (the graph).
        search (dict[str, Any]): The search pipeline graph blob ({} = the stock default).
        fields (list[FieldSpec]): The metadata schema.
    """

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
    fields: list[FieldSpec] = Field(default_factory=list, description="The metadata schema.")


class CreateCollectionRequest(BaseModel):
    """
    Create a collection from A to Z — contract, schema and (optionally) its pipeline.

    Attributes:
        name (str): Unique human name.
        supported_formats (list[str]): Accepted upload extensions (e.g. pdf).
        max_file_size_bytes (int): Upload size ceiling, bytes.
        job_timeout_seconds (float | None): Per-collection whole-ingest-job wall-clock budget,
            seconds. None = inherit the worker's global WORKER_JOB_TIMEOUT_SECONDS default.
        fields (list[FieldSpec]): The FULL schema, declared up front (vector space is fixed).
        pipeline (dict[str, Any] | None): The pipeline blob; omitted → the product default.
    """

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
    fields: list[FieldSpec] = Field(
        default_factory=list,
        description="The FULL schema, declared up front (vector space is fixed at creation).",
    )
    pipeline: dict[str, Any] | None = Field(
        default=None,
        description="The pipeline blob; omitted → the product default (all stages wired).",
    )
    preset: Literal["standard", "light"] | None = Field(
        default=None,
        description="Stock-blob selector (ignored when pipeline is set); 'light' = fast, "
        "enrichment-free core.",
    )


class UpdateCollectionRequest(BaseModel):
    """
    Patch any part of the collection — identity/limits, metadata schema, config blobs.

    Attributes:
        name (str | None): New unique name.
        supported_formats (list[str] | None): New accepted upload extensions.
        max_file_size_bytes (int | None): New size ceiling, bytes.
        job_timeout_seconds (float | None): New per-collection whole-ingest-job wall-clock
            budget, seconds. Omitted = leave the current value unchanged.
        fields (list[FieldSpec] | None): The TARGET schema (diffed by field name).
        pipeline (dict[str, Any] | None): New pipeline blob (validated before storage).
        search (dict[str, Any] | None): New search graph blob ({} = stock default).
        note (str | None): Version note shown in the history.
    """

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
    fields: list[FieldSpec] | None = Field(
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


__all__ = [
    "FieldSpec",
    "CollectionModel",
    "CreateCollectionRequest",
    "UpdateCollectionRequest",
]
