# ====== Code Summary ======
# TableData model: structured content of a TABLE block in the DocForge IR.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class TableData(BaseModel):
    """Structured content of a TABLE block."""

    cells: list[list[str]] = Field(
        ...,
        description="Row-major 2D list of cell strings (native or TableFormer output).",
    )
    n_rows: int
    n_cols: int
    has_header: bool
