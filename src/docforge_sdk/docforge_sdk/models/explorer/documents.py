# ====== Code Summary ======
# Explorer document models: the catalogue list item, the per-document detail with resolved
# metadata, a page's render reference and the heading outline.

# ====== Standard Library Imports ======
from datetime import datetime
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from .._shared import DocumentStatus, FieldOrigin, SourceKind


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
