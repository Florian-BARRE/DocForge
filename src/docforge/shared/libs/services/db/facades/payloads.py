# ====== Code Summary ======
# The transfer objects crossing the façade boundary: IngestionPayload bundles everything the worker
# persists at the end of a pure pipeline run (one transaction), IRBundle is the full raw+enriched
# IR for inspection, ChunkToggle is one chunk's enable/disable outcome. Plain dataclasses over the
# ORM rows — the façade methods stay readable instead of taking fifteen parameters.

# ====== Standard Library Imports ======
import uuid
from dataclasses import dataclass, field
from enum import StrEnum

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql.tables import (
    Block,
    BlockEnrichment,
    BlockFigure,
    BlockTable,
    Chunk,
    ChunkBlock,
    ChunkMetadata,
    Document,
    DocumentMetadata,
    Job,
    MetadataField,
    Page,
    SourceKind,
)


@dataclass(slots=True)
class IngestionPayload:
    """Everything a pipeline run produced for one document — persisted in ONE transaction."""

    # Facts the pipeline learned (None = not learned / unchanged).
    title: str | None = None
    language: str | None = None
    page_count: int | None = None
    source_kind: SourceKind | None = None
    pdf_blob_hash: str | None = None
    simhash: str | None = None
    # The rows, per domain.
    pages: list[Page] = field(default_factory=list)
    document_metadata: list[DocumentMetadata] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)
    block_tables: list[BlockTable] = field(default_factory=list)
    block_figures: list[BlockFigure] = field(default_factory=list)
    enrichments: list[BlockEnrichment] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    composition: list[ChunkBlock] = field(default_factory=list)
    chunk_metadata: list[ChunkMetadata] = field(default_factory=list)


@dataclass(slots=True)
class IRBundle:
    """A document's full IR for inspection — the raw parse side and the enriched side."""

    blocks: list[Block]
    tables: list[BlockTable]
    figures: list[BlockFigure]
    enrichments: list[BlockEnrichment]


@dataclass(slots=True)
class CollectionUpdateSpec:
    """
    Every part of a collection PATCH, to apply in ONE Postgres transaction.

    A collection PATCH can touch four independent things — identity/limits, the metadata schema, the
    config blobs (+ snapshot) and the cost-estimate overrides. Applied as separate transactions, a
    mid-sequence failure leaves a half-patched collection. This bundle lets the façade commit them all
    together (all-or-nothing). Each part is gated by an explicit ``*_touched`` / ``apply_*`` marker so
    an OMITTED part is left untouched, while an explicitly-CLEARED one (e.g. ``estimate_overrides=None``
    with ``apply_overrides=True``) still writes.

    Attributes:
        contract_touched (bool): Apply the identity/limits fields below (each None = leave unchanged).
        name / supported_formats / max_file_size_bytes / job_timeout_seconds: identity/limits values.
        schema_fields (list[MetadataField] | None): The desired metadata schema (None = don't touch
            the schema; a diff-update is applied otherwise).
        config_touched (bool): Apply the pipeline/search blobs below and append a version snapshot.
        pipeline / search (dict | None): The stamped config blobs (None = leave that blob unchanged).
        embed_reindex (bool | None): needs_reindex to set from an embed-space change (None = leave).
        note (str | None): The snapshot note stored with the config version.
        apply_overrides (bool): Write the cost-estimate overrides below (True even to CLEAR to None).
        estimate_overrides (dict | None): The overrides to store (None clears back to the defaults).
    """

    # identity/limits (each None = leave unchanged)
    contract_touched: bool = False
    name: str | None = None
    supported_formats: list[str] | None = None
    max_file_size_bytes: int | None = None
    job_timeout_seconds: float | None = None
    # metadata schema (None = don't touch the schema)
    schema_fields: list[MetadataField] | None = None
    # config blobs (+ immutable snapshot)
    config_touched: bool = False
    pipeline: dict | None = None
    search: dict | None = None
    embed_reindex: bool | None = None
    note: str | None = None
    # cost-estimate overrides (apply=True writes even a clearing None)
    apply_overrides: bool = False
    estimate_overrides: dict | None = None


@dataclass(slots=True)
class CollectionUpdateResult:
    """
    What an atomic collection update changed — drives the post-commit store follow-through.

    Attributes:
        schema_applied (bool): The schema-diff part ran (the router then reconciles Qdrant + backfills
            AFTER the commit — that step is non-transactional and stays OUT of the DB tx).
        schema_reindex_required (bool): The searchable metadata surface changed (a reindex is due).
    """

    schema_applied: bool
    schema_reindex_required: bool


@dataclass(slots=True)
class ChunkToggle:
    """
    The outcome of toggling one chunk's searchability.

    Attributes:
        chunk_id (uuid.UUID): The toggled chunk.
        enabled (bool): The recomputed EFFECTIVE state (override ?? role default).
        reindex_required (bool): True only when enabling a chunk that was never embedded (it has
            no Qdrant point yet, so it is NOT searchable until a later on-demand re-embed runs).
    """

    chunk_id: uuid.UUID
    enabled: bool
    reindex_required: bool


@dataclass(slots=True)
class ChunkToggleResult:
    """
    The outcome of a bulk chunk enable/disable across the two stores (Postgres + Qdrant).

    A chunk toggle writes Postgres (the SOURCE OF TRUTH — the ``enabled_override``) and then flips the
    ``enabled`` scalar on each chunk's EXISTING Qdrant point. The two stores cannot be committed
    atomically (no 2-phase commit across Postgres + Qdrant), so the design is CONVERGENT, not
    falsely-atomic: Postgres commits FIRST, then the Qdrant sync runs off the committed truth. The
    Qdrant flip is idempotent (a pure ``set_payload`` merge of the ``enabled`` key), so re-running the
    same toggle — or the collection backfill/reconcile — heals any divergence. When the Qdrant step
    fails AFTER the Postgres commit, this reports ``search_sync_pending=True`` rather than pretending
    full success (or rolling back as if nothing happened): Postgres reflects the toggle, but the search
    store is stale until a re-run reconciles it.

    Attributes:
        outcomes (list[ChunkToggle]): One outcome per KNOWN chunk (unknown ids are omitted).
        search_sync_pending (bool): True when Postgres committed but the Qdrant payload flip failed —
            the search store is stale and will be reconciled on a re-run or backfill.
        search_sync_error (str | None): The Qdrant failure message when ``search_sync_pending`` is set.
    """

    outcomes: list[ChunkToggle]
    search_sync_pending: bool = False
    search_sync_error: str | None = None


class ReingestOutcome(StrEnum):
    """Why a reingest admission did — or did not — mint a fresh ingestion job."""

    # A fresh job was minted (the document was idle) — enqueue it.
    ADMITTED = "admitted"
    # The document id does not exist — a 404 (single) / silent skip (bulk).
    NOT_FOUND = "not_found"
    # The document already has a live (PENDING/RUNNING) job — refuse rather than run two concurrent
    # runs of one document (they strand orphan Qdrant points). A 409 (single) / skip-with-reason (bulk).
    ALREADY_ACTIVE = "already_active"


@dataclass(slots=True)
class ReingestResult:
    """
    The outcome of a reingest admission — a fresh job, an unknown id, or a refused duplicate run.

    Attributes:
        outcome (ReingestOutcome): Which of the three admission cases occurred.
        document (Document | None): The re-admitted document (ADMITTED only).
        job (Job | None): The freshly-minted job (ADMITTED only).
        active_job_id (uuid.UUID | None): The already-live job that blocked admission (ALREADY_ACTIVE).
    """

    outcome: ReingestOutcome
    document: Document | None = None
    job: Job | None = None
    active_job_id: uuid.UUID | None = None


@dataclass(slots=True)
class AdmissionResult:
    """
    The outcome of a document admission — a fresh admit, or an idempotent duplicate.

    A concurrent upload of the same (collection, source_hash, pipeline_version) can slip between the
    router's dedup pre-check and the insert; the loser hits the document UNIQUE constraint. Rather
    than surface that race as a 500, ``admit`` resolves it to the already-admitted document so a
    client retry stays idempotent — this result tells the two cases apart.

    Attributes:
        created (bool): True when this call inserted the document and minted its job; False when a
            concurrent admission won the race and this call resolved to the incumbent document.
        document (Document | None): The admitted (created=True) or incumbent (created=False) document.
        job (Job | None): The freshly-minted ingestion job (created=True only; None on a duplicate).
    """

    created: bool
    document: Document | None = None
    job: Job | None = None


__all__ = [
    "IngestionPayload",
    "IRBundle",
    "CollectionUpdateSpec",
    "CollectionUpdateResult",
    "ChunkToggle",
    "ChunkToggleResult",
    "ReingestOutcome",
    "ReingestResult",
    "AdmissionResult",
]
