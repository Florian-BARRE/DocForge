# ====== Code Summary ======
# The clean, qdrant-free filter model applied to the FILTERABLE payload fields at search time. A
# filter is a list of conditions ANDed together — exact match, set membership, or a numeric range —
# expressed on a field name + value(s). `PayloadType` names how a filterable field is indexed in
# Qdrant so range/exact filters actually work (a number needs an INTEGER/FLOAT index, not KEYWORD).
# The search api translates these into qdrant-client structs; callers never touch qdrant types.

# ====== Standard Library Imports ======
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class PayloadType(StrEnum):
    """How a filterable field is indexed in Qdrant (drives which filters it supports)."""

    KEYWORD = "keyword"    # string / keyword_list → exact match, set membership
    INTEGER = "integer"    # integer → exact match, range
    FLOAT = "float"        # float → range
    BOOL = "bool"          # boolean → exact match
    DATETIME = "datetime"  # datetime → range
    TEXT = "text"          # long text → full-text match (tokenised index)


@dataclass(slots=True)
class Match:
    """Exact match — ``field == value`` (keyword / bool / integer)."""

    field: str
    value: Any


@dataclass(slots=True)
class MatchAny:
    """Set membership — ``field`` is one of ``values`` (keyword one-of, or keyword_list overlap)."""

    field: str
    values: list[Any]


@dataclass(slots=True)
class Range:
    """Numeric or datetime range on a field — any bound may be None (bounds must not mix kinds)."""

    field: str
    gte: float | datetime | None = None
    lte: float | datetime | None = None
    gt: float | datetime | None = None
    lt: float | datetime | None = None

    @property
    def is_datetime(self) -> bool:
        """Whether this range is over datetimes (drives the qdrant struct to emit)."""
        return any(isinstance(bound, datetime) for bound in (self.gte, self.lte, self.gt, self.lt))


# A filter is a list of these conditions, ANDed together (Qdrant ``must``).
type Condition = Match | MatchAny | Range


__all__ = ["PayloadType", "Match", "MatchAny", "Range", "Condition"]
