# ====== Code Summary ======
# The clean, qdrant-free filter model applied to the FILTERABLE payload fields at search time. A
# filter is a list of conditions ANDed together — exact match, set membership, full-text match, or a
# numeric/datetime range — expressed on a field name + value(s). A request value shapes the condition:
# a scalar → an exact Match, a list → a MatchAny (any-of), a mapping of gte/gt/lte/lt bounds → a Range
# (the bound kind is inferred — an ISO-8601 string is a datetime bound, a number a numeric one); a
# field the caller names as FULL-TEXT indexed (text / text_list) → a MatchText instead of an exact match. `PayloadType`
# names how a filterable field is indexed in Qdrant so range/exact filters actually work (a number
# needs an INTEGER/FLOAT index, a datetime a DATETIME index, not KEYWORD). The search api translates
# these into qdrant-client structs; callers never touch qdrant types.

# ====== Standard Library Imports ======
from collections.abc import Collection, Mapping
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


# A filter is a list of these conditions, ANDed together (Qdrant ``must``).
type Condition = Match | MatchAny | MatchText | Range


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


def build_match_conditions(
    filters: dict[str, Any] | None, text_fields: Collection[str] = ()
) -> list[Condition]:
    """
    Translate a ``{field: value}`` filter map into typed equality/membership/text/range conditions.

    A scalar value becomes an exact ``Match``; a list value becomes a set-membership ``MatchAny``
    (any-of); a MAPPING with range keys (``gte``/``gt``/``lte``/``lt``) becomes a numeric or
    datetime ``Range`` (the bound kind is inferred from the values — an ISO-8601 string is a
    datetime bound, a number a numeric bound). A field named in ``text_fields`` is FULL-TEXT indexed
    in Qdrant (text / text_list), where an exact match on the whole sentence would almost never hit:
    its scalar or list value becomes a ``MatchText`` (any-of the given texts). Filterability and
    range-typing are the caller's concern (the search route gates them and 422s a bad request BEFORE
    this runs) — this pure mapping trusts the fields it is handed and drops nothing.

    Args:
        filters (dict | None): The requested constraints (field name → scalar, list, or range map).
        text_fields (Collection[str]): The filtered fields that carry a full-text payload index.

    Returns:
        list[Condition]: One condition per field, ANDed together (empty for an empty/None map).

    Raises:
        ValueError: On a malformed range mapping, or an EMPTY list value — an empty any-of would
            otherwise translate to an empty Qdrant ``should``, which Qdrant reads as "no
            constraint" and so silently widens the search (defensive — the route 422s both first,
            so a query-path caller never triggers this).
    """
    # 1. One condition per requested field — mapping → range, text field → full-text match,
    #    list → any-of, scalar → exact match. An empty list can never mean "match anything".
    conditions: list[Condition] = []
    for name, value in (filters or {}).items():
        if isinstance(value, list) and not value:
            raise ValueError(f"filter on field '{name}' has an empty value list (matches nothing)")
        if isinstance(value, Mapping):
            conditions.append(parse_range(name, value))
        elif name in text_fields:
            items = value if isinstance(value, list) else [value]
            conditions.append(MatchText(field=name, texts=[str(item) for item in items]))
        elif isinstance(value, list):
            conditions.append(MatchAny(field=name, values=value))
        else:
            conditions.append(Match(field=name, value=value))
    return conditions


__all__ = [
    "PayloadType",
    "Match",
    "MatchAny",
    "MatchText",
    "Range",
    "Condition",
    "RANGE_KEYS",
    "parse_range",
    "build_match_conditions",
]
