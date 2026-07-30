# ====== Code Summary ======
# Where a block physically sits in the source document — page + normalized bounding box, plus an
# optional character span in the flat serialized view. Parser-agnostic: every parser reports a
# block's position this way.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class Provenance(BaseModel):
    """Physical location of a block within the source document."""

    page: int = Field(description="0-indexed page number in the source document.")
    bbox: tuple[float, float, float, float] = Field(
        description="Normalized bounding box (x0, y0, x1, y1) in [0, 1] coordinates."
    )
    char_span: tuple[int, int] | None = Field(
        default=None,
        description="Character span within the flat serialized view, when available.",
    )


__all__ = ["Provenance"]
