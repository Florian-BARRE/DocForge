# ====== Code Summary ======
# Pydantic request/response models of the query-less chunk browse — a filter map in, one ordered page
# of chunks out. A browsed chunk IS a search hit (SearchHitModel) without a score, so a client parses
# both reads with one model.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field

# ====== Internal Project Imports ======
from ..search.models import SearchHint, SearchHitModel


class ChunkBrowseRequest(BaseModel):
    """
    List a collection's chunks by filter, without a query.

    Attributes:
        filters (dict | None): The same filter map as POST /search (same gate, same resolution).
        limit (int): Page size (1-200, default 20).
        cursor (str | None): The previous page's ``next_cursor``; None = the first page.
        return_fields (list[str] | None): Hit fields to return (as search; ``score`` is not one).
    """

    model_config = ConfigDict(extra="forbid")

    filters: dict[str, Any] | None = Field(
        default=None,
        description="Constraints on the FILTERABLE metadata fields — exactly the grammar of POST "
        "/collections/{id}/search `filters` (same validation, same case-insensitive resolution, "
        "same hints). None → every searchable chunk of the collection.",
    )
    limit: int = Field(default=20, ge=1, le=200, description="Chunks per page (1-200).")
    cursor: str | None = Field(
        default=None,
        description="Opaque cursor: the `next_cursor` of the previous page, sent back unchanged with "
        "the SAME filters. None → the first page. A tampered/foreign cursor → 422.",
    )
    return_fields: list[str] | None = Field(
        default=None,
        max_length=64,
        description="The chunk fields to return — any search hit field name except score "
        "(chunk_id, document_id, filename, document_title, heading_path, metadata, text, "
        "chunk_index, token_count, block_ids, page, page_number, bbox, block_locations) or "
        "'metadata.<field>'. chunk_id and document_id are ALWAYS returned. None → every field "
        "EXCEPT the geometry ones (block_ids, page, bbox, block_locations) — page_number is kept "
        "for citation. Omitted fields are absent (not null). An unknown name → 422.",
    )


class ChunkBrowseResponse(BaseModel):
    """
    One page of browsed chunks.

    Attributes:
        chunks (list[SearchHitModel]): The page, ordered by document id then chunk_index.
        next_cursor (str | None): Pass back as ``cursor`` for the next page; None on the last page.
        hints (list[SearchHint]): Filter hints (a value nothing stores; the culprit of an empty page).
    """

    chunks: list[SearchHitModel] = Field(
        default_factory=list,
        description="The chunks of this page in browse order — document id ascending, then "
        "chunk_index ascending. Same shape as a search hit, WITHOUT a score (no query, no ranking: "
        "the key is absent).",
    )
    next_cursor: str | None = Field(
        default=None,
        description="Opaque cursor of the next page (send it as `cursor` with the same filters); "
        "null on the last page.",
    )
    hints: list[SearchHint] = Field(
        default_factory=list,
        description="Filter hints, as search: a filter value no document stores (with the closest "
        "stored values), or the likely culprit filter when the first page is empty.",
    )


__all__ = ["ChunkBrowseRequest", "ChunkBrowseResponse"]
