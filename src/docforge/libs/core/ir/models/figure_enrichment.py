# ====== Code Summary ======
# FigureEnrichment model: enrichment slots for a FIGURE block, populated by S2.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from .enums import FigureKind


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
