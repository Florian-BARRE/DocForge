# ====== Code Summary ======
# The transfer objects crossing the façade boundary: IngestionPayload bundles everything the worker
# persists at the end of a pure pipeline run (one transaction), IRBundle is the full raw+enriched
# IR for inspection, ChunkToggle is one chunk's enable/disable outcome. Plain dataclasses over the
# ORM rows — the façade methods stay readable instead of taking fifteen parameters.

# ====== Standard Library Imports ======
import uuid
from dataclasses import dataclass, field

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql.tables import (
    Block,
    BlockEnrichment,
    BlockFigure,
    BlockTable,
    Chunk,
    ChunkBlock,
    ChunkMetadata,
    DocumentMetadata,
    EnrichmentAttempt,
    EntityMention,
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
    attempts: list[EnrichmentAttempt] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    composition: list[ChunkBlock] = field(default_factory=list)
    chunk_metadata: list[ChunkMetadata] = field(default_factory=list)
    entities: list[EntityMention] = field(default_factory=list)


@dataclass(slots=True)
class IRBundle:
    """A document's full IR for inspection — the raw parse side and the enriched side."""

    blocks: list[Block]
    tables: list[BlockTable]
    figures: list[BlockFigure]
    enrichments: list[BlockEnrichment]
    # The per-enrichment model-chain trace (one row per model tried, in order) — the "enriched by
    # which model / OCR, and what escalated before it" provenance surfaced by the IR inspection view.
    attempts: list[EnrichmentAttempt] = field(default_factory=list)


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


__all__ = ["IngestionPayload", "IRBundle", "ChunkToggle"]
