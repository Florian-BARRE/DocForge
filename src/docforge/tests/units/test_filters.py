"""build_match_conditions / parse_range — the pure, qdrant-free query-time filter translator. The
audit flagged that build_match_conditions had NO dedicated test while it is the ONLY query-time
translator; this proves scalar → Match, list → MatchAny, and (the new) range mapping → Range for
numeric AND datetime bounds, plus the malformed-range guards. Pure shared_libs — no fastapi/app."""

from datetime import datetime

import pytest

from shared_libs.services.db.qdrant import (
    Match,
    MatchAny,
    Range,
    build_match_conditions,
    parse_range,
)

# --------------------------------------------------------------------------- #
# scalar / list — the unchanged, backward-compatible shapes
# --------------------------------------------------------------------------- #


def test_none_and_empty_yield_no_conditions() -> None:
    assert build_match_conditions(None) == []
    assert build_match_conditions({}) == []


def test_scalar_becomes_exact_match() -> None:
    conditions = build_match_conditions({"author": "kafka"})
    assert conditions == [Match(field="author", value="kafka")]


def test_list_becomes_any_of_matchany() -> None:
    conditions = build_match_conditions({"tags": ["law", "audit"]})
    assert conditions == [MatchAny(field="tags", values=["law", "audit"])]


# --------------------------------------------------------------------------- #
# numeric range
# --------------------------------------------------------------------------- #


def test_numeric_range_becomes_a_numeric_range_condition() -> None:
    (cond,) = build_match_conditions({"pages": {"gte": 10, "lt": 100}})
    assert isinstance(cond, Range)
    assert cond.field == "pages"
    assert cond.gte == 10.0
    assert cond.lt == 100.0
    assert cond.lte is None and cond.gt is None
    # A number range is NOT a datetime range — the search api emits a numeric qdrant Range.
    assert cond.is_datetime is False


def test_single_bound_numeric_range_is_valid() -> None:
    (cond,) = build_match_conditions({"score": {"gt": 0.5}})
    assert isinstance(cond, Range)
    assert cond.gt == 0.5


# --------------------------------------------------------------------------- #
# datetime range
# --------------------------------------------------------------------------- #


def test_datetime_range_becomes_a_datetime_range_condition() -> None:
    (cond,) = build_match_conditions({"published": {"gte": "2024-01-01", "lte": "2024-12-31"}})
    assert isinstance(cond, Range)
    assert cond.gte == datetime(2024, 1, 1)
    assert cond.lte == datetime(2024, 12, 31)
    # An ISO-string range IS a datetime range — the search api emits a qdrant DatetimeRange.
    assert cond.is_datetime is True


def test_datetime_range_accepts_a_full_timestamp() -> None:
    (cond,) = build_match_conditions({"published": {"gt": "2024-06-01T12:30:00"}})
    assert isinstance(cond, Range)
    assert cond.gt == datetime(2024, 6, 1, 12, 30, 0)
    assert cond.is_datetime is True


# --------------------------------------------------------------------------- #
# mixed match + range in one filter map
# --------------------------------------------------------------------------- #


def test_mixed_match_and_range_preserve_order_and_types() -> None:
    conditions = build_match_conditions({"author": "kafka", "pages": {"gte": 5}, "tags": ["law"]})
    assert conditions == [
        Match(field="author", value="kafka"),
        Range(field="pages", gte=5.0),
        MatchAny(field="tags", values=["law"]),
    ]


# --------------------------------------------------------------------------- #
# malformed ranges — parse_range raises ValueError (the route surfaces these as 422)
# --------------------------------------------------------------------------- #


def test_unknown_range_key_raises() -> None:
    with pytest.raises(ValueError, match="unsupported key"):
        parse_range("pages", {"between": 3})


def test_empty_range_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        parse_range("pages", {})


def test_mixed_datetime_and_numeric_bounds_raises() -> None:
    with pytest.raises(ValueError, match="mixes datetime and numeric"):
        parse_range("pages", {"gte": 1, "lte": "2024-01-01"})


def test_lower_bound_greater_than_upper_raises() -> None:
    with pytest.raises(ValueError, match="greater than its upper bound"):
        parse_range("pages", {"gte": 100, "lte": 10})


def test_datetime_lower_bound_greater_than_upper_raises() -> None:
    with pytest.raises(ValueError, match="greater than its upper bound"):
        parse_range("published", {"gte": "2024-12-31", "lte": "2024-01-01"})


def test_boolean_bound_raises() -> None:
    with pytest.raises(ValueError, match="boolean"):
        parse_range("flag", {"gte": True})


def test_non_iso_string_bound_raises() -> None:
    with pytest.raises(ValueError, match="neither a number nor an ISO"):
        parse_range("published", {"gte": "not-a-date"})
