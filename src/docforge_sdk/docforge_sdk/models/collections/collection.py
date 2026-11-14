# ====== Code Summary ======
# Collection models: the full collection contract and its create / update request and response.
# The pipeline (ingest graph) and search blobs are opaque server-shaped JSON, typed as plain dicts.

# ====== Standard Library Imports ======
from datetime import datetime
from typing import Any, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from ..estimate import EstimateOverrides
from ..field_spec import FieldSpec
from ..health import CollectionHealthSummary
from ..schema_ops import FieldOp, SchemaDiff


class CollectionModel(BaseModel):
    """
    One collection — the full contract the UI displays and edits.

    Attributes:
        id (str): The collection's UUID.
        name (str): Unique human name.
        supported_formats (list[str]): Accepted upload extensions (e.g. pdf).
        max_file_size_bytes (int): Upload size ceiling, bytes.
        job_timeout_seconds (float | None): Per-collection whole-ingest-job wall-clock job timeout,
            seconds. None = inherit the worker's global WORKER_JOB_TIMEOUT_SECONDS default.
        needs_reindex (bool): True when a config change requires reindexing.
        missing_vectors (list[str] | None): Named vectors the schema's semantic/lexical fields need
            but the vector store does not declare (an index rebuild is required); None on list rows.
        aliases (list[str] | None): The collection aliases targeting it (single read only).
        created_at (datetime | None): Creation timestamp.
        title_field (str | None): Document-scope field used as the display title (None = parsed).
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
            "Per-collection whole-ingest-job wall-clock job timeout, seconds. None = inherit the "
            "worker's global WORKER_JOB_TIMEOUT_SECONDS default."
        ),
    )
    trace_verbosity: Literal["shape", "full"] = Field(
        default="shape",
        description=(
            "Execution-trace capture level for this collection's ingest runs: 'shape' (default) "
            "keeps only the cheap inline shape summary of each node's input/output; 'full' also "
            "stores the raw payload in the object store (clamped by the operator ceiling "
            "WORKER_TRACE_MAX_VERBOSITY)."
        ),
    )
    needs_reindex: bool = Field(description="True when a config change requires reindexing.")
    missing_vectors: list[str] | None = Field(
        default=None,
        description="Named Qdrant vectors (meta_<slug>_dense / meta_<slug>_bm25) the schema's "
        "semantic/lexical fields need but the vector store does not declare — those fields are not "
        "searchable until the collection's index is rebuilt (a reingest cannot add them). Computed "
        "on the single-collection read and the PATCH response ([] = aligned or never ingested); "
        "null on the fleet list, which never reads the vector store.",
    )
    aliases: list[str] | None = Field(
        default=None,
        description="The collection aliases pointing at this collection (each usable in place of the "
        "UUID in every collection route and as an 'alias:<name>' key scope). Computed on the "
        "single-collection read (GET /collections/{id}); null on the other payloads.",
    )
    created_at: datetime | None = Field(default=None, description="Creation timestamp.")
    title_field: str | None = Field(
        default=None,
        description="Document-scope field whose value is each document's display title (None = the "
        "parser-derived title).",
    )
    pipeline: dict[str, Any] | None = Field(
        description="The ingestion pipeline blob (the graph); null when the calling key lacks the "
        "read_technical capability (withheld, not refused)."
    )
    search: dict[str, Any] | None = Field(
        description="The search pipeline graph blob ({} = use the stock default); null when the "
        "calling key lacks the read_technical capability (withheld, not refused)."
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
        job_timeout_seconds (float | None): Per-collection whole-ingest-job wall-clock job timeout,
            seconds. None = inherit the worker's global WORKER_JOB_TIMEOUT_SECONDS default.
        title_field (str | None): Document-scope field used as the display title.
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
            "Per-collection whole-ingest-job wall-clock job timeout, seconds. None = inherit the "
            "worker's global WORKER_JOB_TIMEOUT_SECONDS default."
        ),
    )
    trace_verbosity: Literal["shape", "full"] = Field(
        default="shape",
        description=(
            "Execution-trace capture level for this collection's ingest runs: 'shape' (default) "
            "keeps only the cheap inline shape summary of each node's input/output; 'full' also "
            "stores the raw payload in the object store (clamped by the operator ceiling "
            "WORKER_TRACE_MAX_VERBOSITY)."
        ),
    )
    title_field: str | None = Field(
        default=None,
        description="Document-scope field whose value is each document's display title (must name a "
        "document-scope field of the schema); None = the parser-derived title.",
    )
    fields: list[FieldSpec] = Field(
        default_factory=list,
        description="The FULL schema, declared up front (vector space is fixed at creation).",
    )
    pipeline: dict[str, Any] | None = Field(
        default=None,
        description="The pipeline blob; omitted → the product default (all stages wired).",
    )
    preset: Literal["standard", "light", "ocr_scan", "high_precision"] | None = Field(
        default=None,
        description="Stock INGESTION-blob selector (ignored when pipeline is set): 'standard' (full "
        "default), 'light' (fast, enrichment-free core), 'ocr_scan' (local OCR pass for scanned "
        "docs) or 'high_precision' (finer chunks). Discover via GET /pipelines/ingest → presets.",
    )
    search_preset: Literal["hybrid", "hybrid_rerank", "dense_only"] | None = Field(
        default=None,
        description="Stock SEARCH-blob selector applied at creation: 'hybrid' (default dense+sparse "
        "fusion), 'hybrid_rerank' (hybrid + cross-encoder rerank) or 'dense_only' (pure semantic). "
        "Omitted → the stock hybrid default. Discover via GET /pipelines/search → presets.",
    )


class UpdateCollectionRequest(BaseModel):
    """
    Patch any part of the collection — identity/limits, metadata schema, config blobs.

    Attributes:
        name (str | None): New unique name.
        supported_formats (list[str] | None): New accepted upload extensions.
        max_file_size_bytes (int | None): New size ceiling, bytes.
        job_timeout_seconds (float | None): New per-collection whole-ingest-job wall-clock
            job timeout, seconds. Omitted = leave the current value unchanged.
        title_field (str | None): Display-title field. Omitted = unchanged; explicit null = clear.
        fields (list[FieldSpec] | None): LEGACY full TARGET schema (omitted fields are removed).
        field_ops (list[FieldOp] | None): Explicit add/update/remove/rename ops (exclusive with
            ``fields``).
        dry_run (bool): Preview only — the response's ``schema_diff`` is computed, nothing written.
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
            "New per-collection whole-ingest-job wall-clock job timeout, seconds. Omitted = leave the "
            "current value unchanged; a set value overrides the global WORKER_JOB_TIMEOUT_SECONDS."
        ),
    )
    trace_verbosity: Literal["shape", "full"] | None = Field(
        default=None,
        description=(
            "New execution-trace capture level ('shape' or 'full'); omitted = leave the current "
            "value unchanged. 'full' also stores raw node payloads, clamped by the operator "
            "ceiling WORKER_TRACE_MAX_VERBOSITY."
        ),
    )
    title_field: str | None = Field(
        default=None,
        description="Document-scope field shown as each document's display title. Omitted = leave "
        "unchanged; explicit null = clear (back to the parsed title); a name must be a document-scope "
        "field of the post-PATCH schema. Auto-cleared when that field is removed or renamed.",
    )
    fields: list[FieldSpec] | None = Field(
        default=None,
        description="LEGACY full TARGET schema (omitted fields are REMOVED with their values). "
        "Prefer field_ops. Mutually exclusive with field_ops.",
    )
    field_ops: list[FieldOp] | None = Field(
        default=None,
        description="Explicit schema operations applied in order (add / update / remove / rename). "
        "Mutually exclusive with fields.",
    )
    dry_run: bool = Field(
        default=False,
        description="Validate and compute schema_diff only — nothing is written.",
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


class UpdateCollectionResponse(CollectionModel):
    """
    The PATCH result: the collection (unchanged under dry_run) plus its schema diff.

    Attributes:
        schema_diff (SchemaDiff): The schema change applied (or previewed); empty when untouched.
        dry_run (bool): True when nothing was written.
    """

    schema_diff: SchemaDiff = Field(description="The metadata-schema change applied or previewed.")
    dry_run: bool = Field(description="True when nothing was written (preview only).")
