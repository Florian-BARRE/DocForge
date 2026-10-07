"""DisplayTitleResolver: a collection's title_field wins over the parser title when it holds a value."""

import pytest

from shared_libs.public_models import DisplayTitleResolver


def test_no_title_field_keeps_parsed_title() -> None:
    assert (
        DisplayTitleResolver.resolve("1 GÉNÉRALITÉS", {"nom": "Passation"}, None) == "1 GÉNÉRALITÉS"
    )


def test_title_field_value_wins() -> None:
    metadata = {"nom": "Passation des marchés"}
    assert DisplayTitleResolver.resolve("1 GÉNÉRALITÉS", metadata, "nom") == "Passation des marchés"


@pytest.mark.parametrize("value", [None, "", "   ", []])
def test_blank_or_missing_value_falls_back(value) -> None:
    assert DisplayTitleResolver.resolve("Parsed", {"nom": value}, "nom") == "Parsed"


def test_missing_field_falls_back() -> None:
    assert DisplayTitleResolver.resolve("Parsed", {}, "nom") == "Parsed"


def test_list_value_joins() -> None:
    assert DisplayTitleResolver.resolve(None, {"tags": ["a", " b ", ""]}, "tags") == "a, b"


def test_scalar_non_string_stringifies() -> None:
    assert DisplayTitleResolver.resolve(None, {"year": 2025}, "year") == "2025"
