# ====== Code Summary ======
# The figure slot of a FIGURE block. The PARSE stage completes it: `crop` carries the cropped image
# BYTES (the IR leaves parse "ultra complet" — every figure ready to be worked on). The enrich
# stage fills the meaning later (kind refined by classify, ocr_text / description / data_table).
# The worker stores the crop as a blob at persist time (block_figure.crop_blob_hash).

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from .enums import FigureKind


class FigureEnrichment(BaseModel):
    """Figure slot — the crop bytes from parse, the meaning from enrichment."""

    kind: FigureKind = Field(
        default=FigureKind.PHOTO,
        description="Visual category; a parse-time placeholder until classify refines it.",
    )
    crop: bytes | None = Field(
        default=None, description="PNG bytes of the cropped figure region (set by the parse stage)."
    )
    relevance: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Classifier confidence; gates whether OCR/VLM run on this figure.",
    )
    ocr_text: str | None = Field(
        default=None, description="Text extracted from inside the figure by an OCR provider."
    )
    description: str | None = Field(
        default=None,
        description="VLM caption grounded on the image + ocr_text, written for retrieval.",
    )
    data_table: list[list[str]] | None = Field(
        default=None, description="Chart-to-data extraction: series as a row-major grid."
    )


__all__ = ["FigureEnrichment"]
