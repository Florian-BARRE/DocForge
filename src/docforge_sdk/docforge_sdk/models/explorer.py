# ====== Code Summary ======
# Response/request models for the document explorer resource, mirrored field-for-field from the
# DocForge backend router models: the catalogue list item, the per-document detail + resolved
# metadata, a page's render reference, a chunk with its composition, and the chunk-toggle contract.

# ====== Standard Library Imports ======
from datetime import datetime
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from ._shared import DocumentStatus, FieldOrigin, SourceKind


class MetadataValue(BaseModel):
    """
    One resolved metadata value — the field name, the stored value and the origin that filled it.

    Attributes:
        field_name (str): The schema field this value fills.
        value (Any): The stored JSON value (typed by the field).
        origin (FieldOrigin): Who filled it: user / system / generated.
    """

    field_name: str = Field(description="The schema field this value fills.")
    value: Any = Field(description="The stored JSON value (typed by the field).")
    origin: FieldOrigin = Field(description="Who filled it: user / system / generated.")


class DocumentListItem(BaseModel):
    """
    One row of a collection's document catalogue (the browse list).

    Attributes:
        id (str): The document's UUID.
        filename (str): The uploaded file name.
        format (str): The file extension (pdf, docx, …).
        status (DocumentStatus): Ingestion lifecycle state.
        page_count (int | None): Pages once parsed (None before).
        file_size (int): Original size in bytes.
        created_at (datetime | None): Admission timestamp.
        title (str): Raw parsed title ('' before parse).
        display_title (str): The title to display (title_field value, else the parsed title).
        language (str | None): Detected language (None before parse).
        enabled (bool): Document-level searchability toggle.
        chunk_count (int | None): Chunks persisted at ingestion (0 = empty; None = unknown/legacy).
        warning_reason (str | None): Non-fatal warning on a DONE document (e.g. a 0-chunk run).
    """

    id: str = Field(description="The document's UUID.")
    filename: str = Field(description="The uploaded file name.")
    format: str = Field(description="The file extension (pdf, docx, …).")
    status: DocumentStatus = Field(description="Ingestion lifecycle state.")
    page_count: int | None = Field(default=None, description="Pages once parsed (None before).")
    file_size: int = Field(description="Original size in bytes.")
    created_at: datetime | None = Field(default=None, description="Admission timestamp.")
    title: str = Field(description="Raw parsed title ('' before parse).")
    display_title: str = Field(
        default="",
        description="The title to show: the collection's title_field value when set and present, "
        "else the parsed title.",
    )
    language: str | None = Field(default=None, description="Detected language (None before parse).")
    enabled: bool = Field(description="Document-level searchability toggle.")
    chunk_count: int | None = Field(
        default=None,
        description="Chunks persisted at ingestion (0 = empty; None = unknown/legacy or not yet run).",
    )
    warning_reason: str | None = Field(
        default=None,
        description="Non-fatal warning on a DONE document (e.g. a 0-chunk run); None when none.",
    )


class DocumentDetail(BaseModel):
    """
    A document's full facts plus its resolved document-level metadata.

    Attributes:
        id (str): The document's UUID.
        collection_id (str): Owning collection.
        filename (str): The uploaded file name.
        format (str): The file extension.
        mime_type (str): The upload's declared content type.
        file_size (int): Original size in bytes.
        page_count (int | None): Pages once parsed.
        language (str | None): Detected document language.
        title (str): Raw parsed title ('' before parse).
        display_title (str): The title to display (title_field value, else the parsed title).
        source_kind (SourceKind): Acquisition routing.
        status (DocumentStatus): Ingestion lifecycle state.
        source_hash (str): Content address of the original bytes (blob key).
        pdf_blob_hash (str | None): Canonical PDF view blob (or None).
        simhash (str | None): Near-duplicate signature (or None).
        pipeline_version (str): Pipeline config identity the run used.
        created_at (datetime | None): Admission timestamp.
        enabled (bool): Document-level searchability toggle.
        chunk_count (int | None): Chunks persisted at ingestion (0 = empty; None = unknown/legacy).
        warning_reason (str | None): Non-fatal warning on a DONE document (e.g. a 0-chunk run).
        failure_reason (str | None): Why ingestion did not succeed (the failing job's error).
        searchable (bool): Whether the document is actually retrievable now (enabled + done + non-empty).
        metadata (list[MetadataValue]): Document-level values (declared and generated).
    """

    id: str = Field(description="The document's UUID.")
    collection_id: str = Field(description="Owning collection.")
    filename: str = Field(description="The uploaded file name.")
    format: str = Field(description="The file extension.")
    mime_type: str = Field(description="The upload's declared content type.")
    file_size: int = Field(description="Original size in bytes.")
    page_count: int | None = Field(default=None, description="Pages once parsed.")
    language: str | None = Field(default=None, description="Detected document language.")
    title: str = Field(description="Raw parsed title ('' before parse).")
    display_title: str = Field(
        default="",
        description="The title to show: the collection's title_field value when set and present, "
        "else the parsed title.",
    )
    source_kind: SourceKind = Field(description="Acquisition routing.")
    status: DocumentStatus = Field(description="Ingestion lifecycle state.")
    source_hash: str = Field(description="Content address of the original bytes (blob key).")
    pdf_blob_hash: str | None = Field(
        default=None, description="Canonical PDF view blob (or None)."
    )
    simhash: str | None = Field(default=None, description="Near-duplicate signature (or None).")
    pipeline_version: str = Field(description="Pipeline config identity the run used.")
    created_at: datetime | None = Field(default=None, description="Admission timestamp.")
    enabled: bool = Field(description="Document-level searchability toggle.")
    chunk_count: int | None = Field(
        default=None,
        description="Chunks persisted at ingestion (0 = empty; None = unknown/legacy or not yet run).",
    )
    warning_reason: str | None = Field(
        default=None,
        description="Non-fatal warning on a DONE document (e.g. a 0-chunk run); None when none.",
    )
    failure_reason: str | None = Field(
        default=None,
        description="Why ingestion did not succeed (the failing job's error message), surfaced on a "
        "failed/cancelled document so the detail page can explain it; None when it did not fail.",
    )
    searchable: bool = Field(
        description="Whether the document is actually retrievable RIGHT NOW — enabled AND fully "
        "ingested (status done) AND not known-empty. A failed or 0-chunk document is never searchable, "
        "regardless of the 'enabled' toggle (which is only the user's intent).",
    )
    metadata: list[MetadataValue] = Field(
        default_factory=list, description="Document-level values (declared and generated)."
    )


class PageInfo(BaseModel):
    """
    One page's geometry, routing and its render blob reference.

    Attributes:
        page_number (int): 0-based page INDEX (legacy; first page = 0).
        page_label (int): 1-based page number as a reader counts it (cite this).
        width (float | None): Page width in points (None if unknown).
        height (float | None): Page height in points (None if unknown).
        is_scanned (bool): Whether this page was routed as image-only (OCR/VLM).
        language (str | None): Per-page detected language.
        render_blob_hash (str | None): Blob of the rasterized page (None when render was off).
    """

    page_number: int = Field(
        description="0-based page INDEX (first page = 0) — NOT the reader's page number; use "
        "page_label for that."
    )
    # Defaulted (not required) so this SDK still parses responses from pre-0.23 servers that
    # don't send the field yet.
    page_label: int | None = Field(
        default=None,
        description="1-based page number as a reader counts it (= page_number + 1).",
    )
    width: float | None = Field(default=None, description="Page width in points (None if unknown).")
    height: float | None = Field(
        default=None, description="Page height in points (None if unknown)."
    )
    is_scanned: bool = Field(description="Whether this page was routed as image-only (OCR/VLM).")
    language: str | None = Field(default=None, description="Per-page detected language.")
    render_blob_hash: str | None = Field(
        default=None, description="Blob of the rasterized page (None when render was off)."
    )


class ChunkInfo(BaseModel):
    """
    One retrieval chunk — enriched text, composition (block ids) and generated metadata.

    Attributes:
        id (str): The chunk UUID (doubles as the Qdrant point id).
        chunk_index (int): Position of the chunk within the document.
        text (str): The enriched, embedded text.
        token_count (int): Token length of the enriched text.
        is_indexed (bool): Whether the chunk is upserted into Qdrant.
        role (str): Structural classification set by the pipeline.
        enabled (bool): Effective searchability (override when set, else the role default).
        strategy (str): The chunking strategy that produced it.
        parent_id (str | None): Parent chunk (hierarchical chunking).
        block_ids (list[str]): Composing IR block ids, in assembly order.
        metadata (list[MetadataValue]): Per-chunk generated metadata values.
        heading_path (list[str]): The chunk's section breadcrumb (outer→inner headings).
        page (int | None): Page of the chunk's primary block (0-based); None when unlocated.
        page_number (int | None): The same page, 1-based (as a reader counts it); None when unlocated.
    """

    id: str = Field(description="The chunk UUID (doubles as the Qdrant point id).")
    chunk_index: int = Field(description="Position of the chunk within the document.")
    text: str = Field(description="The enriched, embedded text.")
    token_count: int = Field(description="Token length of the enriched text.")
    is_indexed: bool = Field(description="Whether the chunk is upserted into Qdrant.")
    role: str = Field(description="Structural classification set by the pipeline.")
    enabled: bool = Field(description="Effective searchability (override or role default).")
    strategy: str = Field(description="The chunking strategy that produced it.")
    parent_id: str | None = Field(default=None, description="Parent chunk (hierarchical chunking).")
    block_ids: list[str] = Field(
        default_factory=list, description="Composing IR block ids, in assembly (position) order."
    )
    metadata: list[MetadataValue] = Field(
        default_factory=list, description="Per-chunk generated metadata values."
    )
    heading_path: list[str] = Field(
        default_factory=list,
        description="The chunk's section breadcrumb (outer→inner headings); [] when none.",
    )
    page: int | None = Field(
        default=None,
        description="Page of the chunk's primary block (0-based); None when it has no located block.",
    )
    page_number: int | None = Field(
        default=None,
        description="The same page, 1-based (as a reader counts it); None when unlocated.",
    )


class ChunkPage(BaseModel):
    """
    One page of a document's chunks together with the document's total chunk count.

    SDK-only wrapper (not an OpenAPI schema): the REST body is a bare chunk array and the total
    travels in the ``X-Total-Count`` response header.

    Attributes:
        items (list[ChunkInfo]): The chunks of this page, in chunk_index order.
        total (int | None): The document's total chunk count; None against a server that predates
            the header.
    """

    items: list[ChunkInfo] = Field(description="The chunks of this page, in chunk_index order.")
    total: int | None = Field(
        default=None, description="The document's total chunk count (X-Total-Count header)."
    )


class OutlineHeading(BaseModel):
    """
    One heading of a document's table of contents.

    Attributes:
        level (int): Heading depth (1 = top level).
        text (str): The heading text.
        page_number (int | None): 1-based page the heading sits on; None for page-less documents.
        chunk_id (str | None): The first chunk of this section; None when no chunk carries it.
    """

    level: int = Field(description="Heading depth (1 = top level; 1 when the parser set none).")
    text: str = Field(description="The heading text.")
    page_number: int | None = Field(
        default=None, description="1-based page the heading sits on; null for a page-less document."
    )
    chunk_id: str | None = Field(
        default=None, description="The first chunk of this section; null when none carries it."
    )


class DocumentOutline(BaseModel):
    """
    A document's heading tree - the cheap table of contents to read before fetching content.

    Attributes:
        document_id (str): The document's UUID.
        display_title (str): The title to show ('' when none).
        page_count (int | None): Pages of the document; None before parse / for page-less formats.
        headings (list[OutlineHeading]): Every heading, in reading order.
    """

    document_id: str = Field(description="The document's UUID.")
    display_title: str = Field(description="The title to show ('' when none).")
    page_count: int | None = Field(default=None, description="Pages of the document.")
    headings: list[OutlineHeading] = Field(
        default_factory=list, description="Every heading, in reading order ([] when none)."
    )


class ContextChunk(BaseModel):
    """
    One chunk of a context window (lean projection of a chunk).

    Attributes:
        chunk_id (str): The chunk UUID.
        chunk_index (int): Position of the chunk within its document.
        text (str): The chunk's (enriched) text.
        page_number (int | None): 1-based page of the chunk's leading block; None when unlocated.
        heading_path (list[str]): The chunk's section breadcrumb (outer to inner).
        token_count (int): Token length of the text.
        is_target (bool): True for the chunk the window was requested around.
    """

    chunk_id: str = Field(description="The chunk UUID.")
    chunk_index: int = Field(description="Position of the chunk within its document.")
    text: str = Field(description="The chunk's (enriched) text.")
    page_number: int | None = Field(default=None, description="1-based page; null when unlocated.")
    heading_path: list[str] = Field(
        default_factory=list, description="The chunk's section breadcrumb (outer to inner)."
    )
    token_count: int = Field(description="Token length of the text.")
    is_target: bool = Field(description="True for the chunk the window was requested around.")


class ChunkContext(BaseModel):
    """
    A chunk and its neighbours within the same document (a reading window around a search hit).

    Attributes:
        document_id (str): The owning document's UUID.
        display_title (str): The owning document's display title.
        chunks (list[ContextChunk]): The window in chunk_index order, the target flagged.
    """

    document_id: str = Field(description="The owning document's UUID.")
    display_title: str = Field(description="The owning document's display title.")
    chunks: list[ContextChunk] = Field(
        description="The window in chunk_index order, the target flagged is_target."
    )


class ChunkEnabledPatch(BaseModel):
    """
    The desired searchability state for one chunk (its enabled_override).

    Attributes:
        enabled (bool): True to make the chunk searchable, False to hide it.
    """

    enabled: bool = Field(description="True to make the chunk searchable, False to hide it.")


class BulkChunkEnabledPatch(BaseModel):
    """
    Toggle several chunks' searchability to the same state in one call.

    Attributes:
        chunk_ids (list[str]): The chunks to toggle (at least one).
        enabled (bool): The state to apply to every listed chunk.
    """

    chunk_ids: list[str] = Field(min_length=1, description="The chunks to toggle (at least one).")
    enabled: bool = Field(description="The state to apply to every listed chunk.")


class ChunkEnabledResult(BaseModel):
    """
    The outcome of toggling one chunk's searchability.

    Attributes:
        chunk_id (str): The toggled chunk.
        enabled (bool): The recomputed EFFECTIVE state (override ?? role default).
        reindex_required (bool): True when a never-embedded chunk was enabled — needs a re-embed.
        search_sync_pending (bool): Postgres committed the toggle but the Qdrant payload flip failed —
            the search store is stale until a re-run/backfill reconciles it. Meaningful on the
            single-chunk route; in a bulk response the request-level flag is authoritative.
        search_sync_error (str | None): The Qdrant failure message when ``search_sync_pending``.
    """

    chunk_id: str = Field(description="The toggled chunk's UUID.")
    enabled: bool = Field(description="The recomputed effective searchability state.")
    reindex_required: bool = Field(
        description="True when a never-embedded chunk was enabled — needs a deferred re-embed."
    )
    search_sync_pending: bool = Field(
        default=False,
        description="Postgres committed but the Qdrant sync failed — stale until reconciled.",
    )
    search_sync_error: str | None = Field(
        default=None, description="The Qdrant failure message when search_sync_pending is set."
    )


class BulkChunkEnabledResponse(BaseModel):
    """
    The per-chunk outcomes of a bulk toggle plus the ids that did not resolve to a chunk.

    Attributes:
        results (list[ChunkEnabledResult]): One outcome per KNOWN chunk.
        not_found (list[str]): Requested ids with no matching chunk (skipped, not an error).
        search_sync_pending (bool): Postgres committed the toggles but the Qdrant payload sync failed —
            the search store is stale until a re-run/backfill reconciles it (the batch's truth).
        search_sync_error (str | None): The Qdrant failure message when ``search_sync_pending``.
    """

    results: list[ChunkEnabledResult] = Field(
        default_factory=list, description="One outcome per known chunk."
    )
    not_found: list[str] = Field(
        default_factory=list, description="Requested ids with no matching chunk."
    )
    search_sync_pending: bool = Field(
        default=False,
        description="Postgres committed but the Qdrant sync failed — stale until reconciled.",
    )
    search_sync_error: str | None = Field(
        default=None, description="The Qdrant failure message when search_sync_pending is set."
    )


__all__ = [
    "MetadataValue",
    "DocumentListItem",
    "DocumentDetail",
    "PageInfo",
    "ChunkInfo",
    "ChunkPage",
    "OutlineHeading",
    "DocumentOutline",
    "ContextChunk",
    "ChunkContext",
    "ChunkEnabledPatch",
    "BulkChunkEnabledPatch",
    "ChunkEnabledResult",
    "BulkChunkEnabledResponse",
]
