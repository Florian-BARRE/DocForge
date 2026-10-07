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
from .field_spec import FieldSpec
from .health import CollectionHealthSummary
from .reingest import ReingestJobHandle
from .schema_ops import FieldOp, SchemaDiff


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


class BulkReingestRequest(BaseModel):
    """
    The re-run request over a collection's corpus (a full-pipeline re-ingest).

    Attributes:
        document_ids (list[str] | None): The explicit subset to re-run. Omit or null → EVERY document
            in the collection. An empty list is rejected by the API (an ambiguous no-op).
        force (bool): Bypass the stage cache and recompute every stage from scratch (no cache
            read/write). Use to rebuild after a code change that did not bump a node's CACHE_VERSION.
        replay_from (str | None): Replay from this post-IR stage (no re-parse); None = full re-run.
        confirm_estimate (bool): Acknowledge the estimate of a reingest above the confirm threshold.
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
    replay_from: str | None = Field(
        default=None,
        description="Replay only this post-IR stage and its downstream from each document's PERSISTED "
        "IR (no re-parse): one of enrich, chunk, metagen_chunk, metagen_document, embed — as the "
        "collection's pipeline allows (422 lists the allowed stages). Omit for a full re-run.",
    )
    confirm_estimate: bool = Field(
        default=False,
        description="Acknowledge the cost estimate of a LARGE reingest (above the server's confirm "
        "threshold). Without it such a call is refused 409 estimate_required carrying the estimate "
        "summary; review it and resend with true.",
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
        skipped_in_flight (int): Documents skipped because a run was already active for them.
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
    skipped_in_flight: int = Field(
        default=0,
        description="Documents skipped because an ingestion job was already active for them.",
    )
    skipped_not_replayable: int = Field(
        default=0,
        description="Documents skipped by a replay_from run because they have no persisted IR.",
    )
    jobs: list[ReingestJobHandle] = Field(description="One handle per enqueued run.")


class CollectionContractSchemaResponse(BaseModel):
    """The full discoverable vocabulary of a collection contract — no value has to be guessed."""

    config_schema: dict[str, Any] = Field(
        description="JSON Schema of the collection identity/limits contract (drives the UI form)."
    )
    field_schema: dict[str, Any] = Field(
        description="JSON Schema of one metadata FieldSpec — carries the field_type/origin/scope "
        "enums the identity/limits contract omits."
    )
    supported_format_tokens: list[str] = Field(
        description="Every upload format token a collection may declare in supported_formats "
        "(e.g. 'pdf', 'docx', 'md')."
    )


class FieldGuide(BaseModel):
    """
    One metadata field, described for a client that wants to filter or search on it.

    Attributes:
        name (str): The field name (the key used in ``filters`` / ``search_in``).
        type (FieldType): The declared data type.
        description (str | None): What the field means (None when the schema sets none).
        scope (FieldScope): Where the value lives — one per document, or one per chunk.
        origin (FieldOrigin): Who fills it.
        filterable (bool): Usable as a ``filters`` key.
        semantic (bool): Searchable on its dense vector.
        lexical (bool): Searchable on its sparse vector.
        required (bool): Required at upload.
        enum_values (list[str] | None): The allowed values of an enum field.
        example_values (list[str]): Up to 10 stored values, most frequent first.
        distinct_count (int): Number of distinct stored values.
        note (str | None): Why examples are omitted, when they are.
    """

    name: str = Field(description="The field name (key used in filters / search_in).")
    type: FieldType = Field(description="The declared data type.")
    description: str | None = Field(default=None, description="What the field means.")
    scope: FieldScope = Field(description="One value per document, or one per chunk.")
    origin: FieldOrigin = Field(description="Who fills the field.")
    filterable: bool = Field(description="Usable as a filters key.")
    semantic: bool = Field(description="Searchable on its dense vector.")
    lexical: bool = Field(description="Searchable on its sparse vector.")
    required: bool = Field(description="Required at upload.")
    enum_values: list[str] | None = Field(default=None, description="Allowed values of an enum.")
    example_values: list[str] = Field(
        default_factory=list, description="Up to 10 stored values, most frequent first."
    )
    distinct_count: int = Field(description="Number of distinct stored values.")
    note: str | None = Field(default=None, description="Why examples are omitted, when they are.")


class SearchTargetGuide(BaseModel):
    """
    One valid ``search_in`` entry of the collection.

    Attributes:
        field (str): ``"content"`` (the chunk body) or a metadata field name.
        semantic (bool): The field has a dense vector to query.
        lexical (bool): The field has a sparse vector to query.
    """

    field: str = Field(description="'content' or a metadata field name.")
    semantic: bool = Field(description="The field has a dense vector to query.")
    lexical: bool = Field(description="The field has a sparse vector to query.")


class CollectionDescription(BaseModel):
    """
    The lean agent guide to one collection — what is in it and how to query it.

    Attributes:
        collection_id (str): The collection id.
        name (str): The collection name.
        document_count (int): Number of documents in the collection.
        title_field (str | None): The document-scope field used as each hit's display title.
        page_numbering (str): How hits locate pages (which field to cite).
        fields (list[FieldGuide]): Every metadata field of the schema.
        searchable_targets (list[SearchTargetGuide]): The valid ``search_in`` entries.
        filter_grammar (list[str]): The filter value forms the search route accepts.
        example_requests (list[dict[str, Any]]): Ready-to-send search request bodies.
    """

    collection_id: str = Field(description="The collection id.")
    name: str = Field(description="The collection name.")
    document_count: int = Field(description="Number of documents in the collection.")
    title_field: str | None = Field(default=None, description="Display-title field, if any.")
    page_numbering: str = Field(description="How hits locate pages (which field to cite).")
    fields: list[FieldGuide] = Field(description="Every metadata field of the schema.")
    searchable_targets: list[SearchTargetGuide] = Field(description="Valid search_in entries.")
    filter_grammar: list[str] = Field(description="The accepted filter value forms.")
    example_requests: list[dict[str, Any]] = Field(
        description="Ready-to-send search request bodies for this collection."
    )


__all__ = [
    "FieldSpec",
    "CollectionModel",
    "CollectionListItem",
    "CreateCollectionRequest",
    "UpdateCollectionRequest",
    "UpdateCollectionResponse",
    "BulkReingestRequest",
    "ReingestJobHandle",
    "BulkReingestAccepted",
    "CollectionContractSchemaResponse",
    "FieldGuide",
    "SearchTargetGuide",
    "CollectionDescription",
]
