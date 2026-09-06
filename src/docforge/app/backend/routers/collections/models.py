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
from shared_libs.services.db import (
    CollectionFootprint,
    DocumentFootprint,
    PostgresFootprint,
    QdrantFootprint,
    S3Footprint,
)

# ====== Local Project Imports ======
from ...libs.estimate import EstimateOverrides
from ...libs.health import CollectionHealthSummary


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
    fields: list[FieldSpecModel] = Field(default_factory=list, description="The metadata schema.")
    estimate_overrides: EstimateOverrides | None = Field(
        default=None,
        description="Per-collection PARTIAL cost-estimate overrides (rates/assumptions); null = "
        "use the global defaults.",
    )


class CollectionListItem(CollectionModel):
    """
    One fleet-list row: the full collection contract PLUS its server-computed health summary.

    The list endpoint attaches ``health`` so the dashboard cards render verdict + doc/vector counts +
    last-ingest from the SAME server-side roll-up the collection's own overview (`GET /{id}/health`)
    uses — the two can no longer disagree, and the front no longer fans out N live probes per load.
    """

    health: CollectionHealthSummary = Field(
        description="The collection's rolled-up health verdict + index/doc stats (list-consistent "
        "with the detail probe)."
    )


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

    tags: list[str] | None = Field(
        default=None,
        description="Free-form labels for grouping/filtering ([] / omitted = created untagged).",
    )
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
    estimate_overrides: EstimateOverrides | None = Field(
        default=None,
        description="Partial cost-estimate overrides. Omitted = leave unchanged; explicit null = "
        "clear back to the global defaults; a value replaces the stored overrides.",
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


class S3FootprintModel(BaseModel):
    """EXACT S3 bytes from the content-addressed blob registry (``estimated`` is always false)."""

    original_bytes: int = Field(description="Uploaded source file bytes.")
    rendered_bytes: int = Field(
        description="Derived-blob bytes (canonical PDF, page renders, crops)."
    )
    total_bytes: int = Field(description="Logical bytes (original + rendered).")
    physical_unique_bytes: int = Field(
        description="Deduped disk cost — a blob shared across documents counts once (<= total)."
    )
    estimated: bool = Field(description="Always false: S3 bytes are measured exactly.")

    @classmethod
    def from_payload(cls, payload: S3Footprint) -> "S3FootprintModel":
        """Map the facade dataclass to the response model."""
        return cls(
            original_bytes=payload.original_bytes,
            rendered_bytes=payload.rendered_bytes,
            total_bytes=payload.total_bytes,
            physical_unique_bytes=payload.physical_unique_bytes,
            estimated=payload.estimated,
        )


class PostgresFootprintModel(BaseModel):
    """ESTIMATED Postgres row bytes via ``pg_column_size`` (excludes index/TOAST/bloat)."""

    documents_bytes: int = Field(description="``document`` + ``page`` rows.")
    ir_blocks_bytes: int = Field(description="``block`` + ``block_table`` + ``block_figure`` rows.")
    enrichment_bytes: int = Field(description="``block_enrichment`` rows.")
    chunks_bytes: int = Field(description="``chunk`` + ``chunk_block`` + ``chunk_metadata`` rows.")
    metadata_bytes: int = Field(description="``document_metadata`` rows.")
    observability_bytes: int = Field(description="``job`` + ``job_stage_event`` rows.")
    total_bytes: int = Field(description="Sum of every bucket.")
    estimated: bool = Field(description="Always true: real row bytes, no index/TOAST/bloat.")

    @classmethod
    def from_payload(cls, payload: PostgresFootprint) -> "PostgresFootprintModel":
        """Map the facade dataclass to the response model."""
        return cls(
            documents_bytes=payload.documents_bytes,
            ir_blocks_bytes=payload.ir_blocks_bytes,
            enrichment_bytes=payload.enrichment_bytes,
            chunks_bytes=payload.chunks_bytes,
            metadata_bytes=payload.metadata_bytes,
            observability_bytes=payload.observability_bytes,
            total_bytes=payload.total_bytes,
            estimated=payload.estimated,
        )


class QdrantFootprintModel(BaseModel):
    """ESTIMATED vector-store bytes (points × declared shape — excludes HNSW index overhead)."""

    points: int = Field(description="Point count (collection total, or a document's points).")
    dense_bytes: int = Field(
        description=(
            "On-disk float32 dense bytes, summed per named vector weighted by its carrier count "
            "(content_dense on every point, each meta vector only on its field's documents). "
            "Excludes the int8 quantized RAM-resident copy — this is disk, not RAM."
        )
    )
    sparse_bytes: int = Field(
        description="``points × avg_sparse_entries × 8`` (int32 index + float32 value)."
    )
    payload_bytes: int = Field(description="``points × avg_payload_json_bytes``.")
    total_bytes: int = Field(description="Sum of dense + sparse + payload.")
    estimated: bool = Field(description="Always true: count-based, excludes index overhead.")

    @classmethod
    def from_payload(cls, payload: QdrantFootprint) -> "QdrantFootprintModel":
        """Map the facade dataclass to the response model."""
        return cls(
            points=payload.points,
            dense_bytes=payload.dense_bytes,
            sparse_bytes=payload.sparse_bytes,
            payload_bytes=payload.payload_bytes,
            total_bytes=payload.total_bytes,
            estimated=payload.estimated,
        )


class DocumentStorageModel(BaseModel):
    """One document's footprint across the three stores."""

    document_id: str = Field(description="The document's UUID.")
    filename: str = Field(description="The document's display name.")
    s3: S3FootprintModel = Field(description="EXACT S3 bytes.")
    postgres: PostgresFootprintModel = Field(description="ESTIMATED Postgres row bytes.")
    qdrant: QdrantFootprintModel = Field(description="ESTIMATED vector-store bytes.")
    total_bytes: int = Field(description="S3 (logical) + Postgres + Qdrant.")

    @classmethod
    def from_payload(cls, payload: DocumentFootprint) -> "DocumentStorageModel":
        """Map the facade dataclass to the response model."""
        return cls(
            document_id=str(payload.document_id),
            filename=payload.filename,
            s3=S3FootprintModel.from_payload(payload.s3),
            postgres=PostgresFootprintModel.from_payload(payload.postgres),
            qdrant=QdrantFootprintModel.from_payload(payload.qdrant),
            total_bytes=payload.total_bytes,
        )


class CollectionStorageResponse(BaseModel):
    """
    A collection's material footprint per store, plus the per-document breakdown (heaviest first).

    S3 bytes are EXACT; Postgres and Qdrant bytes are ESTIMATES (each section flags this via
    ``estimated``). ``grand_total_bytes`` uses the DEDUPED S3 disk cost (``physical_unique_bytes``),
    so it reflects real hardware rather than the logical per-document sum.
    """

    collection_id: str = Field(description="The measured collection's UUID.")
    s3: S3FootprintModel = Field(description="EXACT S3 totals (logical + deduped physical).")
    postgres: PostgresFootprintModel = Field(description="ESTIMATED Postgres row bytes.")
    qdrant: QdrantFootprintModel = Field(description="ESTIMATED vector-store bytes.")
    grand_total_bytes: int = Field(
        description="Material footprint — S3 physical_unique + Postgres + Qdrant."
    )
    documents: list[DocumentStorageModel] = Field(
        description="Per-document breakdown, sorted by total bytes descending (doubles as top-N)."
    )

    @classmethod
    def from_payload(cls, payload: CollectionFootprint) -> "CollectionStorageResponse":
        """Map the facade dataclass to the response model."""
        return cls(
            collection_id=str(payload.collection_id),
            s3=S3FootprintModel.from_payload(payload.s3),
            postgres=PostgresFootprintModel.from_payload(payload.postgres),
            qdrant=QdrantFootprintModel.from_payload(payload.qdrant),
            grand_total_bytes=payload.grand_total_bytes,
            documents=[DocumentStorageModel.from_payload(doc) for doc in payload.documents],
        )


__all__ = [
    "FieldSpecModel",
    "CollectionModel",
    "CollectionListItem",
    "CollectionContractModel",
    "CollectionContractSchemaResponse",
    "CreateCollectionRequest",
    "UpdateCollectionRequest",
    "S3FootprintModel",
    "PostgresFootprintModel",
    "QdrantFootprintModel",
    "DocumentStorageModel",
    "CollectionStorageResponse",
]
