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


__all__ = ["TextFilter", "NumberRange", "DateRange", "MetadataFilter", "DocumentFilter"]
