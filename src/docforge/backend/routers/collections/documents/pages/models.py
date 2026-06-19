# ====== Code Summary ======
# Models for the Pages section. A page is a derived view aggregated from the document's blocks
# — not a first-class stored entity.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from pydantic import BaseModel

# ====== Internal Project Imports ======
from ir.models import ChainTrace


class PageInfo(BaseModel):
    """Per-page summary derived from the document's blocks + chunks."""

    page: int
    n_blocks: int
    n_figures: int
    n_tables: int
    has_text: bool
    n_chunks: int


class PageListResponse(BaseModel):
    """All pages of a document with their summaries."""

    document_id: uuid.UUID
    total_pages: int
    pages: list[PageInfo]


class BlockInfo(BaseModel):
    """One IR block on a page — includes type-specific payload for figures and tables."""

    id: str
    type: str
    page: int
    text: str | None = None
    bbox: list[float] = []
    # FIGURE: kind/crop_key/relevance/ocr_text/description/data_table + chain_traces
    # TABLE:  cells/n_rows/n_cols
    type_data: dict | None = None
    # Per-block chain lineage extracted from type_data so the UI doesn't have to
    # know that figure provenance is nested inside the enrichment payload.
    chain_traces: list[ChainTrace] = []


class PageDetailResponse(BaseModel):
    """Full info for one page: blocks + concatenated text + covering chunk ids."""

    document_id: uuid.UUID
    page: int
    n_blocks: int
    blocks: list[BlockInfo]
    text: str
    chunk_ids: list[str]


class PageReingestResponse(BaseModel):
    """Result of a page reingest request (executed as a full-document re-run)."""

    document_id: uuid.UUID
    page: int
    job_id: uuid.UUID
    note: str
