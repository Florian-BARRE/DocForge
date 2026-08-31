# ====== Code Summary ======
# The typed, composable FILTER + SORT + PAGINATION request models for the large-scale document grid.
# Every model is ``extra="forbid"`` (a typo in a filter key is a 422, never a silently dropped
# predicate — mirrors the pipeline blob philosophy). Base columns get purpose-built primitives
# (text contains/eq, numeric/date ranges, enum-set membership, bool); dynamic document-metadata
# fields are addressed by name through an explicit ``MetadataFilter`` (field + op + value) — a
# closed, typed vocabulary, never a free-form DSL. Field-name existence and op/type compatibility
# are resolved against the collection schema by the mapper (a semantic 422), not here.

# ====== Standard Library Imports ======
from datetime import datetime
from typing import Any, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql.tables import DocumentStatus


class TextFilter(BaseModel):
    """A string-column predicate: case-insensitive substring and/or exact match (AND-combined)."""

    model_config = ConfigDict(extra="forbid")

    contains: str | None = Field(default=None, description="Case-insensitive substring match.")
    eq: str | None = Field(default=None, description="Exact match.")


class NumberRange(BaseModel):
    """An inclusive numeric range predicate (either bound may be omitted)."""

    model_config = ConfigDict(extra="forbid")

    gte: float | None = Field(default=None, description="Lower bound, inclusive.")
    lte: float | None = Field(default=None, description="Upper bound, inclusive.")


class DateRange(BaseModel):
    """An inclusive datetime range predicate (either bound may be omitted)."""

    model_config = ConfigDict(extra="forbid")

    gte: datetime | None = Field(default=None, description="Not before this instant (inclusive).")
    lte: datetime | None = Field(default=None, description="Not after this instant (inclusive).")


class MetadataFilter(BaseModel):
    """
    One dynamic document-metadata predicate, addressed by field name.

    Attributes:
        field (str): The metadata field name (must exist in the collection schema + be filterable).
        op (str): The comparison — ``eq``/``contains`` (string/text), ``in`` (membership; matches
            any element for list-typed fields), ``gte``/``lte`` (int/float/datetime).
        value (Any): The comparison value, typed by the field (a list for ``in``).
    """

    model_config = ConfigDict(extra="forbid")

    field: str = Field(description="The metadata field name to filter on.")
    op: Literal["eq", "contains", "in", "gte", "lte"] = Field(description="The comparison operator.")
    value: Any = Field(description="The comparison value (a list for the ``in`` operator).")


class DocumentFilter(BaseModel):
    """
    The per-column filter for one query — every clause is optional and AND-combined.

    An empty filter (all clauses omitted) matches the whole collection, which is exactly what a
    ``DocumentSelector`` in filter mode uses to mean "everything".
    """

    model_config = ConfigDict(extra="forbid")

    filename: TextFilter | None = Field(default=None, description="Filename contains/eq.")
    title: TextFilter | None = Field(default=None, description="Learned title contains/eq.")
    status: list[DocumentStatus] | None = Field(
        default=None, description="Ingestion status membership (pending/processing/done/failed)."
    )
    format: list[str] | None = Field(default=None, description="File-format membership (pdf, docx…).")
    language: list[str] | None = Field(default=None, description="Detected-language membership.")
    file_size: NumberRange | None = Field(default=None, description="Original size range, bytes.")
    page_count: NumberRange | None = Field(default=None, description="Parsed page-count range.")
    created_at: DateRange | None = Field(default=None, description="Admission-timestamp range.")
    enabled: bool | None = Field(default=None, description="Searchability toggle exact match.")
    metadata: list[MetadataFilter] = Field(
        default_factory=list, description="Dynamic document-metadata predicates (AND-combined)."
    )


class DocumentSort(BaseModel):
    """
    The single sort key — a base column OR a document-metadata field name, always id-stabilised.

    ``field`` is a base column (filename, format, status, page_count, file_size, created_at, title,
    language, enabled, id) or a document-metadata field name; the server appends ``id`` as the stable
    secondary key so offset paging never skips or duplicates a row. An unknown field name is a 422.
    """

    model_config = ConfigDict(extra="forbid")

    field: str = Field(default="created_at", description="Base column or metadata field name.")
    direction: Literal["asc", "desc"] = Field(default="desc", description="Sort direction.")


class Pagination(BaseModel):
    """Offset pagination — ``limit`` is clamped server-side to the configured page ceiling."""

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=50, ge=1, description="Page size (clamped to the server ceiling).")
    offset: int = Field(default=0, ge=0, description="Rows to skip (deep offsets are costly — v1).")


class DocumentQueryRequest(BaseModel):
    """The full grid query — filter + sort + pagination (all optional; POST for the structured body)."""

    model_config = ConfigDict(extra="forbid")

    filter: DocumentFilter | None = Field(default=None, description="Per-column filter (AND).")
    sort: DocumentSort | None = Field(default=None, description="Single id-stabilised sort key.")
    pagination: Pagination = Field(default_factory=Pagination, description="Offset pagination.")


__all__ = [
    "TextFilter",
    "NumberRange",
    "DateRange",
    "MetadataFilter",
    "DocumentFilter",
    "DocumentSort",
    "Pagination",
    "DocumentQueryRequest",
]
