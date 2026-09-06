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
from .estimate import EstimateOverrides
from .health import CollectionHealthSummary
from .reingest import ReingestJobHandle


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
        estimate_overrides (EstimateOverrides | None): Per-collection PARTIAL cost-estimate overrides
            (rates/assumptions); null = use the global defaults.
    """

    id: str = Field(description="The collection's UUID.")
    name: str = Field(description="Unique human name.")
    supported_formats: list[str] = Field(description="Accepted upload extensions (e.g. pdf).")
    tags: list[str] = Field(
        default_factory=list,
        description="Free-form labels for grouping/filtering collections in the UI ([] = untagged).",
    )
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
    estimate_overrides: EstimateOverrides | None = Field(
        default=None,
        description="Per-collection PARTIAL cost-estimate overrides (rates/assumptions); null = "
        "use the global defaults.",
    )


class CollectionListItem(CollectionModel):
    """
    One fleet-list row: the full collection contract PLUS its server-computed health summary.

    Attributes:
        health (CollectionHealthSummary): The collection's rolled-up health verdict + index/doc
            stats (list-consistent with the on-demand detail probe).
    """

    health: CollectionHealthSummary = Field(
        description="The collection's rolled-up health verdict + index/doc stats (list-consistent "
        "with the detail probe)."
    )


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
    tags: list[str] | None = Field(
        default=None,
        description="Free-form labels for grouping/filtering ([] / omitted = created untagged).",
    )
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
        estimate_overrides (EstimateOverrides | None): Partial cost-estimate overrides. Omitted =
            leave unchanged; explicit null = clear back to the global defaults; a value replaces
            the stored overrides.
        note (str | None): Version note shown in the history.
    """

    name: str | None = Field(default=None, description="New unique name.")
    supported_formats: list[str] | None = Field(
        default=None, description="New accepted upload extensions."
    )
    tags: list[str] | None = Field(
        default=None,
        description="Replace the collection's labels wholesale ([] clears them); omitted = leave "
        "unchanged.",
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
    estimate_overrides: EstimateOverrides | None = Field(
        default=None,
        description="Partial cost-estimate overrides. Omitted = leave unchanged; explicit null = "
        "clear back to the global defaults; a value replaces the stored overrides.",
    )
    note: str | None = Field(default=None, description="Version note shown in the history.")


class BulkReingestRequest(BaseModel):
    """
    The re-run request over a collection's corpus (a full-pipeline re-ingest).

    Attributes:
        document_ids (list[str] | None): The explicit subset to re-run. Omit or null → EVERY document
            in the collection. An empty list is rejected by the API (an ambiguous no-op).
        force (bool): Bypass the stage cache and recompute every stage from scratch (no cache
            read/write). Use to rebuild after a code change that did not bump a node's CACHE_VERSION.
    """

    document_ids: list[str] | None = Field(
        default=None,
        description="Explicit document UUIDs to re-run; omit for the whole collection.",
    )
    force: bool = Field(
        default=False,
        description="Bypass the stage cache and recompute every stage from scratch (no cache "
        "read/write). Use to rebuild after a code change that did not bump a node's CACHE_VERSION.",
    )


class BulkReingestAccepted(BaseModel):
    """
    The accepted bulk re-run — the runs execute asynchronously (poll each job).

    A match count above the server's per-call fan-out ceiling enqueues only the first N and reports
    ``capped=true`` with the full ``matched`` count, so one call never floods the queue.

    Attributes:
        collection_id (str): The target collection.
        count (int): Jobs enqueued (= ``enqueued``; kept for backward compatibility).
        matched (int): Documents the request resolved to (before the cap).
        enqueued (int): Jobs actually enqueued (<= the fan-out ceiling).
        capped (bool): True when ``matched`` exceeded the per-call fan-out ceiling.
        max_fanout (int): The per-call fan-out ceiling that was applied.
        jobs (list[ReingestJobHandle]): One handle per enqueued run.
    """

    collection_id: str = Field(description="The target collection's UUID.")
    count: int = Field(description="Jobs enqueued (= enqueued; kept for backward compatibility).")
    matched: int = Field(description="Documents the request resolved to (before the cap).")
    enqueued: int = Field(description="Jobs actually enqueued (<= the fan-out ceiling).")
    capped: bool = Field(
        description="True when the match count exceeded the per-call fan-out ceiling."
    )
    max_fanout: int = Field(description="The per-call fan-out ceiling that was applied.")
    jobs: list[ReingestJobHandle] = Field(description="One handle per enqueued run.")


class CollectionContractSchemaResponse(BaseModel):
    """The JSON Schema of the collection identity/limits contract — the discovery payload."""

    config_schema: dict[str, Any] = Field(
        description="JSON Schema of the collection identity/limits contract (drives the UI form)."
    )


__all__ = [
    "FieldSpec",
    "CollectionModel",
    "CollectionListItem",
    "CreateCollectionRequest",
    "UpdateCollectionRequest",
    "BulkReingestRequest",
    "ReingestJobHandle",
    "BulkReingestAccepted",
    "CollectionContractSchemaResponse",
]
