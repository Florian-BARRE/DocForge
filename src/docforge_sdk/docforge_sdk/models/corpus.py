# ====== Code Summary ======
# The typed, composable document-grid FILTER primitives, mirrored field-for-field from the DocForge
# backend (app/backend/libs/corpus/filters.py). Currently consumed by the collection cost-estimate
# request (``CollectionEstimateRequest.filter``); kept in their own module so a future full corpus
# document-grid resource can reuse them without a circular import into ``estimate``.

# ====== Standard Library Imports ======
from datetime import datetime
from typing import Any, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from ._shared import DocumentStatus
from .explorer import DocumentListItem
from .reingest import ReingestJobHandle


class TextFilter(BaseModel):
    """
    A string-column predicate: case-insensitive substring and/or exact match (AND-combined).

    Attributes:
        contains (str | None): Case-insensitive substring match.
        eq (str | None): Exact match.
    """

    contains: str | None = Field(default=None, description="Case-insensitive substring match.")
    eq: str | None = Field(default=None, description="Exact match.")


class NumberRange(BaseModel):
    """
    An inclusive numeric range predicate (either bound may be omitted).

    Attributes:
        gte (float | None): Lower bound, inclusive.
        lte (float | None): Upper bound, inclusive.
    """

    gte: float | None = Field(default=None, description="Lower bound, inclusive.")
    lte: float | None = Field(default=None, description="Upper bound, inclusive.")


class DateRange(BaseModel):
    """
    An inclusive datetime range predicate (either bound may be omitted).

    Attributes:
        gte (datetime | None): Not before this instant (inclusive).
        lte (datetime | None): Not after this instant (inclusive).
    """

    gte: datetime | None = Field(default=None, description="Not before this instant (inclusive).")
    lte: datetime | None = Field(default=None, description="Not after this instant (inclusive).")


class MetadataFilter(BaseModel):
    """
    One dynamic document-metadata predicate, addressed by field name.

    Attributes:
        field (str): The metadata field name (must exist in the collection schema + be filterable).
        op (Literal): The comparison — ``eq``/``contains`` (string/text), ``in`` (membership;
            matches any element for list-typed fields), ``gte``/``lte`` (int/float/datetime).
        value (Any): The comparison value, typed by the field (a list for ``in``).
    """

    field: str = Field(description="The metadata field name to filter on.")
    op: Literal["eq", "contains", "in", "gte", "lte"] = Field(
        description="The comparison operator."
    )
    value: Any = Field(description="The comparison value (a list for the ``in`` operator).")


class DocumentFilter(BaseModel):
    """
    The per-column filter for one query — every clause is optional and AND-combined.

    An empty filter (all clauses omitted) matches the whole collection.

    Attributes:
        filename (TextFilter | None): Filename contains/eq.
        title (TextFilter | None): Learned title contains/eq.
        status (list[DocumentStatus] | None): Ingestion status membership.
        format (list[str] | None): File-format membership (pdf, docx…).
        language (list[str] | None): Detected-language membership.
        file_size (NumberRange | None): Original size range, bytes.
        page_count (NumberRange | None): Parsed page-count range.
        created_at (DateRange | None): Admission-timestamp range.
        enabled (bool | None): Searchability toggle exact match.
        metadata (list[MetadataFilter]): Dynamic document-metadata predicates (AND-combined).
    """

    filename: TextFilter | None = Field(default=None, description="Filename contains/eq.")
    title: TextFilter | None = Field(default=None, description="Learned title contains/eq.")
    status: list[DocumentStatus] | None = Field(
        default=None, description="Ingestion status membership (pending/processing/done/failed)."
    )
    format: list[str] | None = Field(
        default=None, description="File-format membership (pdf, docx…)."
    )
    language: list[str] | None = Field(default=None, description="Detected-language membership.")
    file_size: NumberRange | None = Field(default=None, description="Original size range, bytes.")
    page_count: NumberRange | None = Field(default=None, description="Parsed page-count range.")
    created_at: DateRange | None = Field(default=None, description="Admission-timestamp range.")
    enabled: bool | None = Field(default=None, description="Searchability toggle exact match.")
    metadata: list[MetadataFilter] = Field(
        default_factory=list, description="Dynamic document-metadata predicates (AND-combined)."
    )


class DocumentSort(BaseModel):
    """One id-stabilised sort key: a base column or a metadata field name, plus a direction."""

    field: str = Field(default="created_at", description="Base column or metadata field name.")
    direction: Literal["asc", "desc"] = Field(default="desc", description="Sort direction.")


class Pagination(BaseModel):
    """Offset pagination — ``limit`` is clamped server-side to the configured page ceiling."""

    limit: int = Field(default=50, ge=1, description="Page size (clamped to the server ceiling).")
    offset: int = Field(default=0, ge=0, description="Rows to skip.")


class DocumentQueryRequest(BaseModel):
    """The full grid query — filter + sort + pagination (all optional)."""

    filter: DocumentFilter | None = Field(
        default=None, description="Per-column AND-combined filter."
    )
    sort: DocumentSort | None = Field(default=None, description="Single id-stabilised sort key.")
    pagination: Pagination = Field(default_factory=Pagination, description="Offset pagination.")


class DocumentGridRow(DocumentListItem):
    """One grid row — the catalogue fields plus a compact document-metadata value map."""

    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Document metadata as {field_name: value}."
    )


class DocumentQueryResponse(BaseModel):
    """A page of grid rows plus the total match count and the pagination echo."""

    total: int = Field(description="Total documents matching the filter.")
    limit: int = Field(description="Applied page size (after the server ceiling clamp).")
    offset: int = Field(description="Applied offset.")
    rows: list[DocumentGridRow] = Field(description="The page of rows, in the requested order.")


class DocumentSelector(BaseModel):
    """The shared bulk-op target: an explicit id set XOR a filter (minus a few deselected ids)."""

    document_ids: list[str] | None = Field(
        default=None, description="Explicit target ids (id mode). Mutually exclusive with 'filter'."
    )
    filter: DocumentFilter | None = Field(
        default=None,
        description="Everything matching (filter mode); empty filter = whole collection.",
    )
    exclude_ids: list[str] = Field(
        default_factory=list,
        description="Ids to deselect from the filter result (filter mode only).",
    )


class BulkDeleteResponse(BaseModel):
    """The outcome of a bulk delete — targeted vs actually removed (+ the cap signal)."""

    collection_id: str = Field(description="The target collection's UUID.")
    matched: int = Field(
        description="Documents this call targeted (<= the per-call selection cap)."
    )
    deleted: int = Field(description="Documents actually deleted (PG + Qdrant + S3).")
    capped: bool = Field(
        default=False,
        description="True when the match exceeded the per-call selection cap — more remain; re-run "
        "the same selector to delete them (delete is convergent).",
    )
    max_selection: int = Field(
        default=0, description="The per-call selection cap that was applied."
    )


class BulkEnabledResponse(BaseModel):
    """The outcome of a bulk enable/disable — targeted vs actually changed."""

    collection_id: str = Field(description="The target collection's UUID.")
    enabled: bool = Field(description="The state applied to every target.")
    matched: int = Field(description="Documents the selector resolved to.")
    updated: int = Field(description="Documents whose state actually changed.")
    reindex_implied: bool = Field(description="Always false — a toggle is a flag, not a re-index.")


class BulkReingestResponse(BaseModel):
    """The accepted bulk re-run — targeted vs enqueued, cap flag, and one handle per job."""

    collection_id: str = Field(description="The target collection's UUID.")
    matched: int = Field(description="Documents the selector resolved to.")
    enqueued: int = Field(description="Jobs actually enqueued (<= the fan-out ceiling).")
    capped: bool = Field(description="True when the match exceeded the per-call fan-out ceiling.")
    max_fanout: int = Field(description="The per-call fan-out ceiling applied.")
    jobs: list[ReingestJobHandle] = Field(description="One handle per enqueued run.")


__all__ = [
    "TextFilter",
    "NumberRange",
    "DateRange",
    "MetadataFilter",
    "DocumentFilter",
    "DocumentSort",
    "Pagination",
    "DocumentQueryRequest",
    "DocumentGridRow",
    "DocumentQueryResponse",
    "DocumentSelector",
    "BulkDeleteResponse",
    "BulkEnabledResponse",
    "BulkReingestResponse",
]
