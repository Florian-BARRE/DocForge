# ====== Code Summary ======
# The clean, qdrant-free filter model applied to the FILTERABLE payload fields at search time. A
# filter is a list of conditions ANDed together — exact match, set membership, full-text match, a
# numeric/datetime range, a negation (`Not`, any condition dropped instead of kept), a presence test
# (`IsEmpty`: absent, null or an empty list) — expressed on a field name + value(s). `MatchPattern`
# is an UNRESOLVED contains/prefix on a keyword field: it only exists between the request gate and
# the stored-value expansion, and the search api refuses to translate it. `PayloadType` names how a
# filterable field is indexed in Qdrant so range/exact filters actually work (a number needs an
# INTEGER/FLOAT index, a datetime a DATETIME index, not KEYWORD). The request-value → condition mapping
# lives in filter_builder.py; the search api translates conditions into qdrant-client structs.

# ====== Standard Library Imports ======
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

# The four bound operators a range filter value may carry (any subset, at least one).
RANGE_KEYS: tuple[str, ...] = ("gte", "gt", "lte", "lt")


class PayloadType(StrEnum):
    """How a filterable field is indexed in Qdrant (drives which filters it supports)."""

    KEYWORD = "keyword"  # string / keyword_list → exact match, set membership
    INTEGER = "integer"  # integer → exact match, range
    FLOAT = "float"  # float → range
    BOOL = "bool"  # boolean → exact match
    DATETIME = "datetime"  # datetime → range
    TEXT = "text"  # long text → full-text match (tokenised index)


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
class MatchText:
    """Full-text match on a TEXT-indexed field — any of ``texts`` (each: all its tokens present)."""

    field: str
    texts: list[str]


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


@dataclass(slots=True)
class Not:
    """Negation — a point matching ``condition`` is dropped (Qdrant nested ``must_not``)."""

    condition: "Condition"


@dataclass(slots=True)
class IsEmpty:
    """Presence test — ``field`` is absent, null, or an empty list on the point (Qdrant IsEmpty)."""

    field: str


@dataclass(slots=True)
class MatchPattern:
    """
    An UNRESOLVED ``contains``/``prefix`` on a keyword field.

    Qdrant keyword indexes only match exact values, so the request edge must expand the pattern to
    the stored values it covers (a ``MatchAny``) first. The search api refuses to translate this
    condition — an unexpanded pattern can never silently degrade to an exact match.
    """

    field: str
    operator: str
    needle: str


# A filter is a list of these conditions, ANDed together (Qdrant ``must``).
type Condition = Match | MatchAny | MatchText | Range | Not | IsEmpty | MatchPattern


def _coerce_bound(field: str, key: str, value: Any) -> float | datetime:
    """
    Coerce one range bound to a comparable value — an ISO-8601 string to a datetime, else a float.

    The bound's runtime kind is what drives ``Range.is_datetime`` (and therefore whether the search
    api emits a ``DatetimeRange`` or a numeric ``Range``), so the coercion here IS the datetime
    inference: a number stays numeric, a string must parse as an ISO datetime or the range is bad.

    Args:
        field (str): The field the range is on (for the error message).
        key (str): The bound operator (``gte``/``gt``/``lte``/``lt``) — for the error message.
        value (Any): The raw bound value from the request.

    Returns:
        float | datetime: The coerced bound.

    Raises:
        ValueError: When the value is neither a number nor an ISO-8601 datetime string.
    """
    # 1. Reject booleans first — ``bool`` is an ``int`` subclass and would slip through as 0/1.
    if isinstance(value, bool):
        raise ValueError(
            f"range bound '{key}' on field '{field}' must be a number or ISO datetime, not a boolean"
        )
    # 2. A real number is a numeric bound; a string must be an ISO-8601 datetime.
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                f"range bound '{key}={value!r}' on field '{field}' is neither a number nor an "
                f"ISO-8601 datetime"
            ) from exc
    raise ValueError(
        f"range bound '{key}' on field '{field}' must be a number or ISO datetime, "
        f"not {type(value).__name__}"
    )


def parse_range(field: str, spec: Mapping[str, Any]) -> Range:
    """
    Validate a ``{gte/gt/lte/lt: bound}`` mapping and build the typed ``Range`` condition.

    Args:
        field (str): The field the range constrains.
        spec (Mapping): The range mapping — a non-empty subset of ``RANGE_KEYS`` → bound value.

    Returns:
        Range: The typed range condition (datetime bounds when the values are ISO strings).

    Raises:
        ValueError: On an unknown/empty key set, a non-coercible bound, mixed datetime/numeric
            bounds, or a lower bound greater than the upper bound.
    """
    # 1. Keys must be a non-empty subset of the four range operators.
    unknown = set(spec) - set(RANGE_KEYS)
    if unknown:
        raise ValueError(
            f"range on field '{field}' has unsupported key(s) {sorted(unknown)} — only "
            f"{list(RANGE_KEYS)} are allowed"
        )
    if not spec:
        raise ValueError(
            f"range on field '{field}' is empty — give at least one of {list(RANGE_KEYS)}"
        )
    # 2. Coerce each bound (string → datetime, number → float).
    bounds = {key: _coerce_bound(field, key, spec[key]) for key in spec}
    # 3. A range cannot mix datetime and numeric bounds.
    if len({isinstance(bound, datetime) for bound in bounds.values()}) > 1:
        raise ValueError(f"range on field '{field}' mixes datetime and numeric bounds")
    # 4. The lower bound (gte/gt) must not exceed the upper bound (lte/lt).
    lower = bounds.get("gte", bounds.get("gt"))
    upper = bounds.get("lte", bounds.get("lt"))
    if lower is not None and upper is not None and lower > upper:
        raise ValueError(f"range on field '{field}' has a lower bound greater than its upper bound")
    return Range(field=field, **bounds)


__all__ = [
    "PayloadType",
    "Match",
    "MatchAny",
    "MatchText",
    "Range",
    "Not",
    "IsEmpty",
    "MatchPattern",
    "Condition",
    "RANGE_KEYS",
    "parse_range",
]
