# ====== Code Summary ======
# Pydantic models for the document explorer — the READ surface over one collection's documents:
# the catalogue list item, the per-document facts + resolved metadata, a page's render reference,
# and a chunk with its composition + generated metadata. The IR models live in models_ir.py.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldOrigin
from shared_libs.services.db.postgresql.tables import DocumentStatus, SourceKind


class MetadataValue(BaseModel):
    """
    One resolved metadata value — the field NAME (joined from the collection schema), the stored
    value, and the origin that actually filled THIS value (user upload / pipeline / metagen).
    """

    field_name: str = Field(description="The schema field this value fills.")
    value: Any = Field(description="The stored JSON value (typed by the field).")
    origin: FieldOrigin = Field(description="Who filled it: user / system / generated.")


class DocumentListItem(BaseModel):
    """One row of a collection's document catalogue (the browse list)."""

    id: str = Field(description="The document's UUID.")
    filename: str = Field(description="The uploaded file name.")
    format: str = Field(description="The file extension (pdf, docx, …).")
    status: DocumentStatus = Field(description="Ingestion lifecycle: pending/processing/done/failed.")
    page_count: int | None = Field(default=None, description="Pages once parsed (None before).")
    file_size: int = Field(description="Original size in bytes.")
    created_at: datetime | None = Field(default=None, description="Admission timestamp.")
    title: str = Field(description="Learned title ('' before parse).")
    language: str | None = Field(default=None, description="Detected language (None before parse).")


class DocumentDetail(BaseModel):
    """A document's full facts plus its resolved document-level metadata."""

    id: str = Field(description="The document's UUID.")
    collection_id: str = Field(description="Owning collection.")
    filename: str = Field(description="The uploaded file name.")
    format: str = Field(description="The file extension.")
    mime_type: str = Field(description="The upload's declared content type.")
    file_size: int = Field(description="Original size in bytes.")
    page_count: int | None = Field(default=None, description="Pages once parsed.")
    language: str | None = Field(default=None, description="Detected document language.")
    title: str = Field(description="Learned title ('' before parse).")
    source_kind: SourceKind = Field(description="Acquisition routing: digital_born/scanned/mixed.")
    status: DocumentStatus = Field(description="Ingestion lifecycle state.")
    source_hash: str = Field(description="Content address of the original bytes (blob key).")
    pdf_blob_hash: str | None = Field(default=None, description="Canonical PDF view blob (or None).")
    simhash: str | None = Field(default=None, description="Near-duplicate signature (or None).")
    pipeline_version: str = Field(description="Pipeline config identity the run used.")
    created_at: datetime | None = Field(default=None, description="Admission timestamp.")
    metadata: list[MetadataValue] = Field(
        default_factory=list, description="Document-level values (declared and generated)."
    )


class PageInfo(BaseModel):
    """One page's geometry, routing and its render blob reference."""

    page_number: int = Field(description="0-based page index (first page = 0).")
    width: float | None = Field(default=None, description="Page width in points (None if unknown).")
    height: float | None = Field(default=None, description="Page height in points (None if unknown).")
    is_scanned: bool = Field(description="Whether this page was routed as image-only (OCR/VLM).")
    language: str | None = Field(default=None, description="Per-page detected language.")
    render_blob_hash: str | None = Field(
        default=None, description="Blob of the rasterized page (None when render was off)."
    )


class ChunkInfo(BaseModel):
    """One retrieval chunk — enriched text, composition (block ids) and generated metadata."""

    id: str = Field(description="The chunk UUID (doubles as the Qdrant point id).")
    chunk_index: int = Field(description="Position of the chunk within the document.")
    text: str = Field(description="The enriched, embedded text.")
    token_count: int = Field(description="Token length of the enriched text.")
    is_indexed: bool = Field(description="Whether the chunk is upserted into Qdrant.")
    strategy: str = Field(description="The chunking strategy that produced it.")
    parent_id: str | None = Field(default=None, description="Parent chunk (hierarchical chunking).")
    block_ids: list[str] = Field(
        default_factory=list, description="Composing IR block ids, in assembly (position) order."
    )
    metadata: list[MetadataValue] = Field(
        default_factory=list, description="Per-chunk generated metadata values."
    )


class ChunkEnabledPatch(BaseModel):
    """The desired searchability state for one chunk (its enabled_override)."""

    enabled: bool = Field(description="True to make the chunk searchable, False to hide it.")


class BulkChunkEnabledPatch(BaseModel):
    """Toggle several chunks' searchability to the same state in one call (the UI's multi-select)."""

    chunk_ids: list[uuid.UUID] = Field(
        min_length=1, description="The chunks to toggle (at least one)."
    )
    enabled: bool = Field(description="The state to apply to every listed chunk.")


class ChunkEnabledResult(BaseModel):
    """
    The outcome of toggling one chunk's searchability.

    Attributes:
        chunk_id (str): The toggled chunk.
        enabled (bool): The recomputed EFFECTIVE state (override ?? role default).
        reindex_required (bool): True only when enabling a chunk that was never embedded — it has
            no Qdrant point, so it is NOT searchable until a later on-demand re-embed runs.
    """

    chunk_id: str = Field(description="The toggled chunk's UUID.")
    enabled: bool = Field(description="The recomputed effective searchability state.")
    reindex_required: bool = Field(
        description="True when a never-embedded chunk was enabled — needs a deferred re-embed."
    )


class BulkChunkEnabledResponse(BaseModel):
    """
    The per-chunk outcomes of a bulk toggle plus the ids that did not resolve to a chunk.

    Attributes:
        results (list[ChunkEnabledResult]): One outcome per KNOWN chunk.
        not_found (list[str]): Requested ids with no matching chunk (skipped, not an error).
    """

    results: list[ChunkEnabledResult] = Field(
        default_factory=list, description="One outcome per known chunk."
    )
    not_found: list[str] = Field(
        default_factory=list, description="Requested ids with no matching chunk."
    )


__all__ = [
    "MetadataValue",
    "DocumentListItem",
    "DocumentDetail",
    "PageInfo",
    "ChunkInfo",
    "ChunkEnabledPatch",
    "BulkChunkEnabledPatch",
    "ChunkEnabledResult",
    "BulkChunkEnabledResponse",
]
