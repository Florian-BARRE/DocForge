# ====== Code Summary ======
# Provenance model: physical location of a block within the source document.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


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
