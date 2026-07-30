# ====== Code Summary ======
# Structured content of a TABLE block — a row-major grid of cell strings plus its shape.
# Parser-agnostic: native extraction or a table-structure model both fill it the same way.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class TableData(BaseModel):
    """Structured content of a TABLE block."""

    cells: list[list[str]] = Field(description="Row-major 2D grid of cell strings.")
    n_rows: int
    n_cols: int
    has_header: bool = False


__all__ = ["TableData"]
