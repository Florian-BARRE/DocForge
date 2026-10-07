"""SearchFilterResolver + ZeroHitHintBuilder — the request-edge filter value resolution (Postgres as
the value oracle, faked here): string-ish values canonicalized to the stored spellings, text fields
flagged for full-text matching, numbers/ranges untouched, unmatched values hinted with suggestions,
and the zero-hit "likely culprit" hints."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.libs.search import FilterResolution, SearchFilterResolver, ZeroHitHintBuilder
from shared_libs.public_models import FieldScope, FieldType

_STORED = {"identifiant": ["AFD-P0153", "afd-P0153", "AFD-P0154"], "tags": ["Audit", "Law"]}


def _field(name: str, ftype: FieldType, scope: FieldScope = FieldScope.DOCUMENT):
    return SimpleNamespace(field_name=name, field_type=ftype, filterable=True, scope=scope)


def _schema() -> list:
    return [
        _field("identifiant", FieldType.STRING),
        _field("tags", FieldType.KEYWORD_LIST),
        _field("summary", FieldType.TEXT),
        _field("findings", FieldType.TEXT_LIST, FieldScope.CHUNK),
        _field("year", FieldType.INTEGER),
    ]


def _oracle() -> SimpleNamespace:
    def canonicalize(field, values):
        stored = _STORED.get(field.field_name, [])
        return {v: [s for s in stored if s.lower() == v.lower()] for v in values}

    return SimpleNamespace(
        canonicalize=AsyncMock(side_effect=canonicalize),
        suggest=AsyncMock(return_value=["AFD-P0153", "AFD-P0154"]),
    )


def _resolve(filters: dict | None, oracle: SimpleNamespace | None = None) -> FilterResolution:
    return asyncio.run(SearchFilterResolver(oracle or _oracle()).resolve(filters, _schema()))


def test_wrong_case_value_resolves_to_every_stored_variant() -> None:
    resolution = _resolve({"identifiant": "afd-p0153"})
    assert resolution.filters == {"identifiant": ["AFD-P0153", "afd-P0153"]}
    assert resolution.hints == []


def test_single_variant_scalar_stays_a_scalar() -> None:
    assert _resolve({"identifiant": "afd-p0154"}).filters == {"identifiant": "AFD-P0154"}


def test_keyword_list_items_are_canonicalized() -> None:
    assert _resolve({"tags": ["audit", "LAW"]}).filters == {"tags": ["Audit", "Law"]}


def test_exact_value_is_passed_through_byte_identical() -> None:
    assert _resolve({"identifiant": "AFD-P0154"}).filters == {"identifiant": "AFD-P0154"}


def test_unmatched_value_keeps_literal_and_yields_hint_with_suggestions() -> None:
    resolution = _resolve({"identifiant": "afd-p0153x"})
    assert resolution.filters == {"identifiant": "afd-p0153x"}
    (hint,) = resolution.hints
    assert hint.field == "identifiant" and hint.value == "afd-p0153x"
    assert hint.suggestions == ["AFD-P0153", "AFD-P0154"]
    assert hint.message == (
        'No document has identifiant = "afd-p0153x". Closest stored values: AFD-P0153, AFD-P0154.'
    )


def test_text_fields_are_flagged_and_numbers_ranges_untouched() -> None:
    oracle = _oracle()
    filters = {"summary": "audit", "findings": ["x"], "year": {"gte": 2020}}
    resolution = _resolve(filters, oracle)
    assert resolution.text_fields == frozenset({"summary", "findings"})
    assert resolution.filters == filters
    oracle.canonicalize.assert_not_awaited()


def test_no_filters_means_no_io() -> None:
    oracle = _oracle()
    resolution = _resolve(None, oracle)
    assert resolution.filters == {} and resolution.hints == []
    oracle.canonicalize.assert_not_awaited()


def test_zero_hit_single_filter_is_named_the_likely_culprit() -> None:
    resolution = _resolve({"identifiant": "AFD-P0154"})
    (hint,) = ZeroHitHintBuilder.build(resolution, hit_count=0)
    assert hint.field == "identifiant"
    assert "likely culprit" in hint.message


def test_zero_hit_several_filters_blame_the_combination() -> None:
    resolution = _resolve({"identifiant": "AFD-P0154", "summary": "audit"})
    hints = ZeroHitHintBuilder.build(resolution, hit_count=0)
    assert [h.field for h in hints] == ["identifiant", "summary"]
    assert all("combination" in h.message for h in hints)
    assert "matches text" in hints[1].message


def test_zero_hit_builder_is_silent_when_hits_or_culprit_already_known() -> None:
    matched = _resolve({"identifiant": "AFD-P0154"})
    assert ZeroHitHintBuilder.build(matched, hit_count=3) == []
    unmatched = _resolve({"identifiant": "nope"})
    assert ZeroHitHintBuilder.build(unmatched, hit_count=0) == []
    assert ZeroHitHintBuilder.build(_resolve(None), hit_count=0) == []


def test_suggestions_are_bounded_for_a_huge_unmatched_list() -> None:
    """Each unmatched value used to trigger a suggest() (pool read + difflib + session) — a
    1000-item list must cost at most 5 suggestion lookups; the rest are hinted without them."""
    oracle = _oracle()
    values = [f"bogus-{i}" for i in range(1000)]
    resolution = _resolve({"tags": values}, oracle)
    assert oracle.suggest.await_count == 5
    assert oracle.canonicalize.await_count == 1
    assert len(resolution.hints) == 1000
    assert all(hint.suggestions for hint in resolution.hints[:5])
    assert all(hint.suggestions == [] for hint in resolution.hints[5:])
    assert resolution.hints[999].message == 'No document has tags = "bogus-999".'


def test_hint_quotes_the_value_as_sent_not_the_gated_one() -> None:
    oracle = _oracle()
    resolution = asyncio.run(
        SearchFilterResolver(oracle).resolve(
            {"identifiant": ["x-member"]}, _schema(), sent={"identifiant": ["X-MEMBER"]}
        )
    )
    (hint,) = resolution.hints
    assert hint.value == "X-MEMBER"
    oracle.suggest.assert_awaited_once()
    assert oracle.suggest.await_args.args[1] == "x-member"
    assert resolution.original == {"identifiant": ["X-MEMBER"]}


def test_zero_hit_does_not_claim_existence_for_unverified_filters() -> None:
    """A text/number/range filter is never checked against stored values, so the combination hint
    must not say "Each value exists" — only when every filter's values were verified."""
    resolution = _resolve({"identifiant": "AFD-P0154", "year": {"gte": 2020}})
    hints = ZeroHitHintBuilder.build(resolution, hit_count=0)
    assert all("Each value exists" not in h.message for h in hints)
    assert all("The combination of these filters matches no chunk" in h.message for h in hints)

    verified = _resolve({"identifiant": "AFD-P0154", "tags": ["audit"]})
    assert verified.verified_fields == frozenset({"identifiant", "tags"})
    assert all(
        "Each value exists" in h.message for h in ZeroHitHintBuilder.build(verified, hit_count=0)
    )
