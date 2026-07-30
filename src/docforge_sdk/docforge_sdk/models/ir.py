# ====== Code Summary ======
# Response models for the document IR view (GET /documents/{id}/ir), mirrored field-for-field from the
# DocForge backend router models. Table cells and enrichment data are opaque server-shaped JSON, so
# they are typed as ``Any`` rather than a structured grid model.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from ._shared import EnrichmentKind, EnrichmentStatus


class IRBlock(BaseModel):
    """
    One RAW IR block — structure, position in reading order and native text.

    Attributes:
        id (str): Document-namespaced block id.
        block_type (str): text / heading / list / table / figure / …
        page (int): 0-based page the block sits on (first page = 0).
        bbox (list[float]): Bounding box [x0, y0, x1, y1] in page coordinates.
        reading_order (int): Global reading-order rank within the document.
        column_index (int): Column the block belongs to (multi-column layouts).
        parent_id (str | None): Parent block in the heading tree.
        level (int | None): Heading level (None for non-headings).
        text (str | None): Native extracted text (None for figures).
        is_boilerplate (bool): Flagged repeated header/footer/watermark.
        language (str | None): Per-block detected language.
        confidence (float | None): Parser confidence (None if n/a).
    """

    id: str = Field(description="Document-namespaced block id.")
    block_type: str = Field(description="text / heading / list / table / figure / …")
    page: int = Field(description="0-based page the block sits on (first page = 0).")
    bbox: list[float] = Field(description="Bounding box [x0, y0, x1, y1] in page coordinates.")
    reading_order: int = Field(description="Global reading-order rank within the document.")
    column_index: int = Field(description="Column the block belongs to (multi-column layouts).")
    parent_id: str | None = Field(default=None, description="Parent block in the heading tree.")
    level: int | None = Field(default=None, description="Heading level (None for non-headings).")
    text: str | None = Field(default=None, description="Native extracted text (None for figures).")
    is_boilerplate: bool = Field(description="Flagged repeated header/footer/watermark.")
    language: str | None = Field(default=None, description="Per-block detected language.")
    confidence: float | None = Field(default=None, description="Parser confidence (None if n/a).")


class IRTable(BaseModel):
    """
    A TABLE block's parsed structure (1:1 with its block).

    Attributes:
        block_id (str): The TABLE block this detail belongs to.
        n_rows (int): Row count of the grid.
        n_cols (int): Column count of the grid.
        has_header (bool): Whether the first row is a header.
        cells (Any): Row-major 2D cell grid (opaque JSON).
        linearized_md (str | None): Deterministic markdown rendering.
    """

    block_id: str = Field(description="The TABLE block this detail belongs to.")
    n_rows: int = Field(description="Row count of the grid.")
    n_cols: int = Field(description="Column count of the grid.")
    has_header: bool = Field(description="Whether the first row is a header.")
    cells: Any = Field(description="Row-major 2D cell grid (opaque JSON).")
    linearized_md: str | None = Field(default=None, description="Deterministic markdown rendering.")


class IRFigure(BaseModel):
    """
    A FIGURE block's parse-time facts (1:1 with its block).

    Attributes:
        block_id (str): The FIGURE block this detail belongs to.
        crop_blob_hash (str | None): Blob of the cropped figure image (None if not stored).
        caption_block_id (str | None): The associated caption block id.
    """

    block_id: str = Field(description="The FIGURE block this detail belongs to.")
    crop_blob_hash: str | None = Field(
        default=None, description="Blob of the cropped figure image (None if not stored)."
    )
    caption_block_id: str | None = Field(
        default=None, description="The associated caption block id (proximity + numbering)."
    )


class IREnrichment(BaseModel):
    """
    One enrichment applied to a block (OCR/VLM/classify/chart_to_data/table_summary).

    Attributes:
        id (str): The enrichment UUID (use it to fetch the model-chain trace).
        block_id (str): The enriched block.
        kind (EnrichmentKind): What the enrichment produced.
        text (str | None): OCR text / VLM description (None if data-only).
        data (Any | None): Structured result (chart cells, classification).
        status (EnrichmentStatus): ok / failed / skipped.
    """

    id: str = Field(description="The enrichment UUID (use it to fetch the model-chain trace).")
    block_id: str = Field(description="The enriched block.")
    kind: EnrichmentKind = Field(description="What the enrichment produced.")
    text: str | None = Field(
        default=None, description="OCR text / VLM description (None if data-only)."
    )
    data: Any | None = Field(
        default=None, description="Structured result (chart cells, classification)."
    )
    status: EnrichmentStatus = Field(description="ok / failed / skipped.")


class DocumentIRModel(BaseModel):
    """
    The full IR of a document — raw blocks, table/figure details and every enrichment.

    Attributes:
        blocks (list[IRBlock]): Raw blocks, reading order.
        tables (list[IRTable]): Table detail rows.
        figures (list[IRFigure]): Figure detail rows.
        enrichments (list[IREnrichment]): Every block enrichment (OCR/VLM/…).
    """

    blocks: list[IRBlock] = Field(default_factory=list, description="Raw blocks, reading order.")
    tables: list[IRTable] = Field(default_factory=list, description="Table detail rows.")
    figures: list[IRFigure] = Field(default_factory=list, description="Figure detail rows.")
    enrichments: list[IREnrichment] = Field(
        default_factory=list, description="Every block enrichment (OCR/VLM/…)."
    )


__all__ = [
    "IRBlock",
    "IRTable",
    "IRFigure",
    "IREnrichment",
    "DocumentIRModel",
]
