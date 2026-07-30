"""SearchHelpers.validate_search_targets / to_search_targets — the store-free 422 guard the search
route runs BEFORE any spend, and the pure request → public SearchTarget mapper. Lightweight
stand-ins (matching the `.field_name`/`.semantic`/`.lexical` reads) stand in for MetadataField rows.
``from backend...`` deferred until fastapi_app registered app/ on sys.path."""

from types import SimpleNamespace


def _field(name: str, semantic: bool = False, lexical: bool = False) -> SimpleNamespace:
    return SimpleNamespace(field_name=name, semantic=semantic, lexical=lexical)


def _schema() -> list[SimpleNamespace]:
    return [
        _field("author", semantic=True, lexical=False),
        _field("tags", semantic=False, lexical=True),
        _field("plain", semantic=False, lexical=False),
    ]


def _target_model(**kwargs):
    from backend.routers.search.models import SearchTargetModel  # noqa: PLC0415

    return SearchTargetModel(**kwargs)


def test_search_in_none_yields_no_errors(fastapi_app) -> None:
    from backend.routers.search.helpers import SearchHelpers  # noqa: PLC0415

    assert SearchHelpers.validate_search_targets(None, _schema()) == []


def test_unknown_field_is_an_error(fastapi_app) -> None:
    from backend.routers.search.helpers import SearchHelpers  # noqa: PLC0415

    errors = SearchHelpers.validate_search_targets(
        [_target_model(field="bogus", semantic=True)], _schema()
    )
    assert any("unknown field" in e for e in errors)


def test_target_with_no_modality_is_an_error(fastapi_app) -> None:
    from backend.routers.search.helpers import SearchHelpers  # noqa: PLC0415

    errors = SearchHelpers.validate_search_targets(
        [_target_model(field="author", semantic=False, lexical=False)], _schema()
    )
    assert any("selects no modality" in e for e in errors)


def test_semantic_on_non_semantic_field_is_an_error(fastapi_app) -> None:
    from backend.routers.search.helpers import SearchHelpers  # noqa: PLC0415

    errors = SearchHelpers.validate_search_targets(
        [_target_model(field="tags", semantic=True)], _schema()
    )
    assert any("no semantic" in e for e in errors)


def test_lexical_on_non_lexical_field_is_an_error(fastapi_app) -> None:
    from backend.routers.search.helpers import SearchHelpers  # noqa: PLC0415

    errors = SearchHelpers.validate_search_targets(
        [_target_model(field="author", lexical=True)], _schema()
    )
    assert any("no lexical" in e for e in errors)


def test_valid_metadata_target_yields_no_errors(fastapi_app) -> None:
    from backend.routers.search.helpers import SearchHelpers  # noqa: PLC0415

    errors = SearchHelpers.validate_search_targets(
        [_target_model(field="author", semantic=True)], _schema()
    )
    assert errors == []


def test_to_search_targets_none_passes_through(fastapi_app) -> None:
    from backend.routers.search.helpers import SearchHelpers  # noqa: PLC0415

    assert SearchHelpers.to_search_targets(None) is None


def test_to_search_targets_round_trips_a_list(fastapi_app) -> None:
    from backend.routers.search.helpers import SearchHelpers  # noqa: PLC0415

    models = [_target_model(field="author", semantic=True, lexical=False)]
    targets = SearchHelpers.to_search_targets(models)
    assert targets is not None
    assert len(targets) == 1
    assert targets[0].field == "author"
    assert targets[0].semantic is True
    assert targets[0].lexical is False
