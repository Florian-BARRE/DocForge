"""The filter-operator grammar ({field: {"<op>": value}}) — pure, qdrant-free: FilterOperatorGrammar
validation messages (unknown op, op not valid for the field type, forbidden combinations, malformed
operands, range typing), build_match_conditions mapping every operator to its condition, and the
search api translation (Not → nested must_not, IsEmpty, DatetimeRange only for datetime bounds, an
unexpanded keyword pattern refused)."""

from datetime import datetime

import pytest
from qdrant_client import models

from shared_libs.services.db.qdrant import (
    FilterOperatorGrammar,
    IsEmpty,
    Match,
    MatchAny,
    MatchPattern,
    MatchText,
    Not,
    PayloadType,
    QdrantSearchApi,
    Range,
    build_match_conditions,
)

# --------------------------------------------------------------------------- #
# FilterOperatorGrammar.validate — the 422 messages
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("ptype", "spec"),
    [
        (PayloadType.KEYWORD, {"in": ["a"]}),
        (PayloadType.KEYWORD, {"not": "a"}),
        (PayloadType.KEYWORD, {"not_in": ["a", "b"]}),
        (PayloadType.KEYWORD, {"contains": "a"}),
        (PayloadType.KEYWORD, {"prefix": "a"}),
        (PayloadType.KEYWORD, {"exists": False}),
        (PayloadType.TEXT, {"contains": "audit rights"}),
        (PayloadType.INTEGER, {"not_in": [1, 2]}),
        (PayloadType.INTEGER, {"gte": 1, "lte": 9}),
        (PayloadType.DATETIME, {"gte": "2024-01-01", "lt": "2024-02-01"}),
        (PayloadType.BOOL, {"not": True}),
        (PayloadType.FLOAT, {"exists": True}),
    ],
)
def test_valid_operator_objects_have_no_violation(ptype, spec) -> None:
    assert FilterOperatorGrammar.validate("f", spec, ptype) == []


def test_unknown_operator_lists_the_valid_ones_for_the_type() -> None:
    (error,) = FilterOperatorGrammar.validate("year", {"between": 3}, PayloadType.INTEGER)
    assert "unsupported key" in error and "'between'" in error
    assert "'gte'" in error and "'not_in'" in error and "'prefix'" not in error


@pytest.mark.parametrize(
    ("ptype", "spec", "op"),
    [
        (PayloadType.INTEGER, {"prefix": "1"}, "prefix"),
        (PayloadType.TEXT, {"prefix": "au"}, "prefix"),
        (PayloadType.DATETIME, {"eq": "2024-01-01"}, "eq"),
        (PayloadType.BOOL, {"in": [True]}, "in"),
    ],
)
def test_operator_not_valid_for_the_field_type(ptype, spec, op) -> None:
    (error,) = FilterOperatorGrammar.validate("f", spec, ptype)
    assert f"operator '{op}' is not valid on a {ptype.value} field" in error


def test_range_and_another_operator_cannot_combine() -> None:
    (error,) = FilterOperatorGrammar.validate("year", {"gte": 1, "not": 3}, PayloadType.INTEGER)
    assert "cannot be combined" in error


def test_two_non_range_operators_cannot_combine() -> None:
    (error,) = FilterOperatorGrammar.validate("t", {"in": ["a"], "not": "b"}, PayloadType.KEYWORD)
    assert "cannot be combined" in error


def test_range_on_a_keyword_field_is_not_range_typed() -> None:
    (error,) = FilterOperatorGrammar.validate("author", {"gte": "a"}, PayloadType.KEYWORD)
    assert "not range-typed (keyword)" in error


def test_untyped_field_gets_a_clean_message_not_a_crash() -> None:
    assert "not range-typed (untyped)" in FilterOperatorGrammar.validate("x", {"gte": 1}, None)[0]
    assert (
        "not valid on a untyped field" in FilterOperatorGrammar.validate("x", {"in": [1]}, None)[0]
    )


@pytest.mark.parametrize(
    ("spec", "fragment"),
    [
        ({}, "empty operator object"),
        ({"exists": "yes"}, "'exists' takes true/false"),
        ({"prefix": "  "}, "'prefix' takes a non-empty string"),
        ({"contains": 3}, "'contains' takes a non-empty string"),
        ({"in": []}, "'in' takes a non-empty list"),
        ({"not_in": "a"}, "'not_in' takes a non-empty list"),
        ({"in": list(range(101))}, "exceed the maximum of 100"),
        ({"not": ["a"]}, "takes scalar value(s)"),
        ({"eq": None}, "takes scalar value(s)"),
    ],
)
def test_malformed_operands(spec, fragment) -> None:
    (error,) = FilterOperatorGrammar.validate("f", spec, PayloadType.KEYWORD)
    assert fragment in error


def test_range_bound_kind_must_match_the_field() -> None:
    assert (
        "ISO-8601 datetime"
        in FilterOperatorGrammar.validate("p", {"gte": 1}, PayloadType.DATETIME)[0]
    )
    assert (
        "numeric"
        in FilterOperatorGrammar.validate("y", {"gte": "2024-01-01"}, PayloadType.INTEGER)[0]
    )


# --------------------------------------------------------------------------- #
# build_match_conditions — operator → condition
# --------------------------------------------------------------------------- #


def test_eq_and_in_match_the_bare_forms() -> None:
    assert build_match_conditions({"a": {"eq": "x"}, "b": {"in": ["x", "y"]}}) == [
        Match(field="a", value="x"),
        MatchAny(field="b", values=["x", "y"]),
    ]


def test_not_and_not_in_wrap_the_positive_condition() -> None:
    assert build_match_conditions({"a": {"not": "x"}, "b": {"not_in": ["x", "X"]}}) == [
        Not(condition=Match(field="a", value="x")),
        Not(condition=MatchAny(field="b", values=["x", "X"])),
    ]


def test_exists_maps_to_is_empty() -> None:
    assert build_match_conditions({"a": {"exists": False}, "b": {"exists": True}}) == [
        IsEmpty(field="a"),
        Not(condition=IsEmpty(field="b")),
    ]


def test_text_field_operators_are_full_text() -> None:
    conditions = build_match_conditions(
        {"s": {"contains": "audit"}, "t": {"not_in": ["a", "b"]}}, text_fields={"s", "t"}
    )
    assert conditions == [
        MatchText(field="s", texts=["audit"]),
        Not(condition=MatchText(field="t", texts=["a", "b"])),
    ]


def test_keyword_patterns_stay_unresolved_patterns() -> None:
    assert build_match_conditions({"k": {"prefix": "al"}, "c": {"contains": "ph"}}) == [
        MatchPattern(field="k", operator="prefix", needle="al"),
        MatchPattern(field="c", operator="contains", needle="ph"),
    ]


def test_range_bounds_still_build_a_range() -> None:
    (cond,) = build_match_conditions({"pub": {"gte": "2024-01-01"}})
    assert cond == Range(field="pub", gte=datetime(2024, 1, 1))


def test_an_empty_in_list_raises_never_widens() -> None:
    with pytest.raises(ValueError, match="empty value list"):
        build_match_conditions({"k": {"not_in": []}})


# --------------------------------------------------------------------------- #
# QdrantSearchApi translation
# --------------------------------------------------------------------------- #


def test_not_translates_to_a_nested_must_not() -> None:
    struct = QdrantSearchApi._to_field_condition(Not(condition=MatchAny(field="a", values=["x"])))
    assert struct == models.Filter(
        must_not=[models.FieldCondition(key="a", match=models.MatchAny(any=["x"]))]
    )


def test_is_empty_translates_to_qdrant_is_empty() -> None:
    struct = QdrantSearchApi._to_field_condition(IsEmpty(field="a"))
    assert struct == models.IsEmptyCondition(is_empty=models.PayloadField(key="a"))


def test_an_unexpanded_pattern_is_refused() -> None:
    with pytest.raises(ValueError, match="not expanded to stored values"):
        QdrantSearchApi._to_field_condition(MatchPattern(field="k", operator="prefix", needle="a"))


def test_datetime_range_only_for_datetime_bounds() -> None:
    dt = QdrantSearchApi._to_field_condition(Range(field="p", gte=datetime(2024, 1, 1)))
    num = QdrantSearchApi._to_field_condition(Range(field="y", gte=2020.0))
    assert isinstance(dt.range, models.DatetimeRange)
    assert isinstance(num.range, models.Range) and not isinstance(num.range, models.DatetimeRange)


@pytest.mark.parametrize(
    ("ptype", "spec"),
    [
        # A mistyped exclusion would exclude NOTHING (Qdrant never coerces) — a silent widening.
        (PayloadType.INTEGER, {"not": "2021"}),
        (PayloadType.INTEGER, {"not_in": [2020, "2021"]}),
        (PayloadType.INTEGER, {"not": True}),  # bool is an int subclass — still refused
        (PayloadType.BOOL, {"not": "true"}),
        (PayloadType.KEYWORD, {"not": 5}),
        (PayloadType.TEXT, {"in": [1]}),
        (PayloadType.INTEGER, {"eq": "7"}),
    ],
)
def test_mistyped_operand_is_rejected(ptype, spec) -> None:
    (error,) = FilterOperatorGrammar.validate("f", spec, ptype)
    assert "takes" in error and "value(s)" in error


@pytest.mark.parametrize(
    ("ptype", "spec"),
    [
        (PayloadType.INTEGER, {"not": 2021}),
        (PayloadType.INTEGER, {"in": [1, 2]}),
        (PayloadType.BOOL, {"eq": False}),
        (PayloadType.KEYWORD, {"not_in": ["a"]}),
    ],
)
def test_correctly_typed_operand_is_accepted(ptype, spec) -> None:
    assert FilterOperatorGrammar.validate("f", spec, ptype) == []
