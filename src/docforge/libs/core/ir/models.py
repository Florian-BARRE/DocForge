
# ====== Code Summary ======
# Canonical Intermediate Representation (IR) for DocForge.
# All document parsers produce a DocumentIR; markdown/PDF/HTML are views derived from it.

# ====== Standard Library Imports ======
from enum import StrEnum

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ─── Chain provenance (filled by providers.chain.Chain.call) ────────────────


class ChainAttemptIR(BaseModel):
    """
    Serialisable record of one provider attempt within a stage's chain.

    Mirrors ``providers.chain.ChainAttempt`` so the IR can be persisted as jsonb
    and round-tripped through Postgres without the dataclass dependency.  The
    stage code converts each ``ChainAttempt`` into a ``ChainAttemptIR`` at the
    boundary so the IR layer stays free of provider imports.

    Attributes:
        provider_id (str): Stable identifier of the provider (e.g. ``"docling"``).
        score (float | None): Self-reported quality in ``[0.0, 1.0]`` or None.
        duration_ms (int): Wall-clock duration of this attempt.
        succeeded (bool): False when the call raised or returned None.
        escalated (bool): True when the gate told the chain to try the next provider.
        error (str | None): Exception summary captured when the attempt raised.
        cost_usd (float): Provider-reported cost of this attempt (0.0 if free).
    """

    provider_id: str
    score: float | None = None
    duration_ms: int
    succeeded: bool
    escalated: bool
    error: str | None = None
    cost_usd: float = 0.0


class ChainTrace(BaseModel):
    """
    Full audit trail of one chain invocation, stamped on the IR.

    Stage-level traces (``parse``, ``embed``) live on the ``DocumentIR``; block-level
    traces (``classifier``, ``ocr``, ``vlm``) live on the individual ``Block`` so each
    figure carries its own lineage.

    Attributes:
        stage (str): Stage label (``"parse"``, ``"ocr"``, ``"vlm"``,
            ``"classifier"``, ``"embed"``).
        attempts (list[ChainAttemptIR]): One record per provider tried, in order.
        final_provider (str | None): provider_id of the attempt whose result was
            kept, or None when every provider escalated.
    """

    stage: str
    attempts: list[ChainAttemptIR] = Field(default_factory=list)
    final_provider: str | None = None


class BlockType(StrEnum):
    """Semantic type of a document block."""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE = "table"
    FIGURE = "figure"
    CAPTION = "caption"
    CODE = "code"
    FORMULA = "formula"
    HEADER_FOOTER = "header_footer"  # detected, excluded from chunks by default


class FigureKind(StrEnum):
    """Visual category of a figure block, used to route enrichment (OCR / VLM)."""

    SCANNED_TEXT = "scanned_text"  # text rendered as image (scan region)
    CHART = "chart"                # data visualization (bar, line, pie...)
    DIAGRAM = "diagram"            # schema, flow, architecture drawing
    PHOTO = "photo"                # photographic / illustrative content
    DECORATIVE = "decorative"      # logo, banner, separator → skipped by enrichment


class Provenance(BaseModel):
    """Physical location of a block within the source document."""

    page: int = Field(..., description="0-indexed page number in the source document.")
    bbox: tuple[float, float, float, float] = Field(
        ...,
        description="Normalized bounding box (x0, y0, x1, y1) in [0, 1] coordinates.",
    )
    char_span: tuple[int, int] | None = Field(
        default=None,
        description="Character span within the serialized flat view, if available.",
    )


class FigureEnrichment(BaseModel):
    """Enrichment slots for a FIGURE block; populated by S2 (enrichment stage)."""

    kind: FigureKind
    crop_key: str = Field(
        ...,
        description="Object-store key of the cropped figure image (MinIO).",
    )
    relevance: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Figure classifier confidence score; gates OCR/VLM calls.",
    )
    ocr_text: str | None = Field(
        default=None,
        description="Text extracted from inside the figure by an OCR provider.",
    )
    description: str | None = Field(
        default=None,
        description="VLM caption grounded on ocr_text + image, written for retrieval.",
    )
    data_table: list[list[str]] | None = Field(
        default=None,
        description="Chart-to-data extraction: series as a row-major table.",
    )


class TableData(BaseModel):
    """Structured content of a TABLE block."""

    cells: list[list[str]] = Field(
        ...,
        description="Row-major 2D list of cell strings (native or TableFormer output).",
    )
    n_rows: int
    n_cols: int
    has_header: bool


class Block(BaseModel):
    """Atomic unit of the DocumentIR.  Carries content, provenance, and enrichment slots."""

    id: str = Field(..., description="Unique block identifier within the document.")
    type: BlockType
    prov: Provenance
    reading_order: int = Field(
        ...,
        description="Absolute reading order across all pages (0-indexed).",
    )
    parent_id: str | None = Field(
        default=None,
        description="ID of the parent HEADING block; builds the heading tree.",
    )
    level: int | None = Field(
        default=None,
        description="Heading depth (1 = H1, 2 = H2, …); only set for HEADING blocks.",
    )
    text: str | None = Field(
        default=None,
        description="Native text content for text-bearing blocks.",
    )
    table: TableData | None = Field(
        default=None,
        description="Structured table data; only set for TABLE blocks.",
    )
    figure: FigureEnrichment | None = Field(
        default=None,
        description="Figure enrichment; only set for FIGURE blocks.",
    )
    language: str | None = Field(
        default=None,
        description="ISO 639-1 language code when the block differs from the document language.",
    )
    chain_traces: list[ChainTrace] = Field(
        default_factory=list,
        description=(
            "Per-stage provider chain attempts that touched THIS block "
            "(classifier / ocr / vlm).  Empty by default so existing IR rows still load."
        ),
    )


class DocumentIR(BaseModel):
    """
    Canonical Intermediate Representation of a parsed document.

    This is the pivot of the system.  All downstream stages (enrichment, serialization,
    chunking, embedding) consume the DocumentIR, never the raw source or the flat markdown.
    """

    doc_id: str = Field(..., description="Unique document identifier (UUID).")
    title: str = Field(
        default="",
        description="Document title extracted by the parser (empty when unavailable).",
    )
    source_hash: str = Field(
        ...,
        description="SHA-256 hex digest of the original file bytes; used for content-addressing.",
    )
    pipeline_fingerprints: dict[str, str] = Field(
        default_factory=dict,
        description="Stage name → blake3 fingerprint; tracks which config produced each artifact.",
    )
    n_pages: int = Field(..., description="Total page count.")
    language: str = Field(
        ...,
        description="Dominant ISO 639-1 language code of the document.",
    )
    blocks: list[Block] = Field(
        default_factory=list,
        description="All blocks in reading order; heading tree encoded via parent_id.",
    )
    quality_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Parser-reported quality estimate for THIS IR (e.g. textual blocks / total). "
            "Used by the S1 parse chain's gate to decide escalation."
        ),
    )
    chain_traces: list[ChainTrace] = Field(
        default_factory=list,
        description=(
            "Document-level provider chain attempts (parse, embed).  Empty by "
            "default so legacy IR rows still load."
        ),
    )

    @property
    def heading_blocks(self) -> list[Block]:
        """Return only HEADING blocks, in reading order."""
        return [b for b in self.blocks if b.type == BlockType.HEADING]

    @property
    def figure_blocks(self) -> list[Block]:
        """Return only FIGURE blocks, in reading order."""
        return [b for b in self.blocks if b.type == BlockType.FIGURE]

    @property
    def table_blocks(self) -> list[Block]:
        """Return only TABLE blocks, in reading order."""
        return [b for b in self.blocks if b.type == BlockType.TABLE]
