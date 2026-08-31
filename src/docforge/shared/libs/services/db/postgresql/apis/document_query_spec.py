# ====== Code Summary ======
# The framework-free QUERY SPEC for the large-scale document grid — the plain dataclasses the data
# layer executes against. The backend maps its (Pydantic, extra="forbid") filter/sort request onto
# this spec, resolving every metadata reference to a concrete field_id + FieldType against the
# collection schema FIRST, so DocumentQueryApi never has to touch the schema: it just builds SQL.
# One cohesive module of tightly-related small dataclasses/enums (the general rule's stated exception).

# ====== Standard Library Imports ======
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldType

# ====== Local Project Imports ======
from ..tables import DocumentStatus


class MetadataOp(StrEnum):
    """The comparison a single metadata-field filter applies against its stored JSONB value."""

    EQ = "eq"  # scalar equality (string/enum/bool/int/float)
    CONTAINS = "contains"  # case-insensitive substring (string/text)
    IN = "in"  # membership: scalar in a set, OR any list element in a set (keyword_list…)
    GTE = "gte"  # >= (int/float/datetime)
    LTE = "lte"  # <= (int/float/datetime)


class SortDirection(StrEnum):
    """Sort direction for the (always id-stabilised) ordering."""

    ASC = "asc"
    DESC = "desc"


@dataclass(frozen=True, slots=True)
class MetadataCondition:
    """One resolved metadata-field predicate (the backend already mapped name → id + type)."""

    field_id: int
    field_type: FieldType
    op: MetadataOp
    value: object


@dataclass(frozen=True, slots=True)
class SortSpec:
    """
    The ordering the grid asked for — a base column OR a metadata field, always id-stabilised.

    ``column`` names a base ``document`` column when ``metadata_field_id`` is None; otherwise the
    ordering key is the metadata value of that field (``column`` is then ignored). ``id`` is always
    appended as the deterministic secondary key so offset paging never skips or duplicates a row.
    """

    column: str = "created_at"
    direction: SortDirection = SortDirection.DESC
    metadata_field_id: int | None = None
    metadata_field_type: FieldType | None = None


@dataclass(frozen=True, slots=True)
class DocumentQuerySpec:
    """The fully-resolved filter + sort the data layer executes for one collection's grid."""

    # ── base string columns ──
    filename_contains: str | None = None
    filename_eq: str | None = None
    title_contains: str | None = None
    # ── enum / set columns ──
    statuses: tuple[DocumentStatus, ...] = ()
    formats: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    # ── numeric ranges ──
    file_size_gte: int | None = None
    file_size_lte: int | None = None
    page_count_gte: int | None = None
    page_count_lte: int | None = None
    # ── date range ──
    created_after: datetime | None = None
    created_before: datetime | None = None
    # ── bool ──
    enabled: bool | None = None
    # ── dynamic metadata predicates ──
    metadata: tuple[MetadataCondition, ...] = ()
    # ── ordering ──
    sort: SortSpec = field(default_factory=SortSpec)


__all__ = [
    "MetadataOp",
    "SortDirection",
    "MetadataCondition",
    "SortSpec",
    "DocumentQuerySpec",
]
