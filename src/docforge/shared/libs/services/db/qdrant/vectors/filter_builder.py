# ====== Code Summary ======
# build_match_conditions — the pure request-value → Condition mapping of the search filter map. A
# scalar → Match, a list → MatchAny (any-of), an operator object → its condition: eq/in as the bare
# forms, not/not_in → Not(...), exists → IsEmpty / Not(IsEmpty), range bounds → Range, contains on a
# full-text field → MatchText, contains/prefix on a keyword field → MatchPattern (which the request
# edge must have expanded to stored values first — the search api refuses an unexpanded one). A field
# named FULL-TEXT indexed (text / text_list) matches by MatchText instead of exact equality.

# ====== Standard Library Imports ======
from collections.abc import Collection, Mapping
from typing import Any

# ====== Local Project Imports ======
from .filter_operators import FilterOp, FilterOperatorGrammar
from .filters import (
    Condition,
    IsEmpty,
    Match,
    MatchAny,
    MatchPattern,
    MatchText,
    Not,
    parse_range,
)


def _value_condition(name: str, value: Any, full_text: bool) -> Condition:
    """
    Map a bare scalar / list value to its positive condition.

    Raises:
        ValueError: On an EMPTY list — an empty any-of would reach Qdrant as an empty ``should``,
            which Qdrant reads as "no constraint" and so silently widens the search.
    """
    # 1. An empty list can never mean "match anything".
    if isinstance(value, list) and not value:
        raise ValueError(f"filter on field '{name}' has an empty value list (matches nothing)")
    # 2. Full-text fields match by text; else a list is any-of and a scalar is exact.
    if full_text:
        items = value if isinstance(value, list) else [value]
        return MatchText(field=name, texts=[str(item) for item in items])
    if isinstance(value, list):
        return MatchAny(field=name, values=value)
    return Match(field=name, value=value)


def _operator_condition(name: str, spec: Mapping[str, Any], full_text: bool) -> Condition:
    """
    Map one operator object (``{"<op>": value}`` or range bounds) to its condition.

    Raises:
        ValueError: On a malformed range, or an operator combined with any other key.
    """
    # 1. Bounds only → a range (parse_range rejects unknown keys).
    op = FilterOperatorGrammar.operator_of(spec)
    if op is None:
        return parse_range(name, spec)
    if len(spec) != 1:
        raise ValueError(f"filter on field '{name}' combines operator '{op}' with other keys")
    value = spec[op.value]

    # 2. Positive / negated value matches, presence, then the string patterns.
    if op in (FilterOp.EQ, FilterOp.IN):
        return _value_condition(name, value, full_text)
    if op in (FilterOp.NOT, FilterOp.NOT_IN):
        return Not(condition=_value_condition(name, value, full_text))
    if op is FilterOp.EXISTS:
        return Not(condition=IsEmpty(field=name)) if value else IsEmpty(field=name)
    if op is FilterOp.CONTAINS and full_text:
        return MatchText(field=name, texts=[str(value)])
    return MatchPattern(field=name, operator=op.value, needle=str(value))


def build_match_conditions(
    filters: dict[str, Any] | None, text_fields: Collection[str] = ()
) -> list[Condition]:
    """
    Translate a ``{field: value}`` filter map into typed conditions (one per field, ANDed).

    Filterability, operator validity and range typing are the caller's concern (the search route
    gates them and 422s a bad request BEFORE this runs) — this pure mapping trusts the fields it is
    handed and drops nothing.

    Args:
        filters (dict | None): The requested constraints (field → scalar, list or operator object).
        text_fields (Collection[str]): The filtered fields that carry a full-text payload index.

    Returns:
        list[Condition]: One condition per field (empty for an empty/None map).

    Raises:
        ValueError: On a malformed operator object or range, or an EMPTY list value.
    """
    # 1. One condition per requested field — operator object, or bare scalar/list.
    conditions: list[Condition] = []
    for name, value in (filters or {}).items():
        full_text = name in text_fields
        if isinstance(value, Mapping):
            conditions.append(_operator_condition(name, value, full_text))
        else:
            conditions.append(_value_condition(name, value, full_text))
    return conditions


__all__ = ["build_match_conditions"]
