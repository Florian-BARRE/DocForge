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


# --------------------------------------------------------------------------- #
# range_violations — the 422 gate for range ({gte/gt/lte/lt}) filter mappings
# --------------------------------------------------------------------------- #


def _typed_field(name: str, field_type, filterable: bool = True) -> SimpleNamespace:
    return SimpleNamespace(field_name=name, field_type=field_type, filterable=filterable)


def _range_schema() -> list[SimpleNamespace]:
    from shared_libs.public_models import FieldType  # noqa: PLC0415

    return [
        _typed_field("pages", FieldType.INTEGER),
        _typed_field("score", FieldType.FLOAT),
        _typed_field("published", FieldType.DATETIME),
        _typed_field("author", FieldType.STRING),  # keyword — NOT range-typed
    ]


def test_numeric_range_on_integer_field_is_valid(fastapi_app) -> None:
    from backend.routers.search.helpers import SearchHelpers  # noqa: PLC0415

    assert SearchHelpers.range_violations({"pages": {"gte": 1, "lte": 9}}, _range_schema()) == []


def test_datetime_range_on_datetime_field_is_valid(fastapi_app) -> None:
    from backend.routers.search.helpers import SearchHelpers  # noqa: PLC0415

    errors = SearchHelpers.range_violations(
        {"published": {"gte": "2024-01-01", "lte": "2024-12-31"}}, _range_schema()
    )
    assert errors == []


def test_range_on_keyword_field_is_rejected(fastapi_app) -> None:
    from backend.routers.search.helpers import SearchHelpers  # noqa: PLC0415

    errors = SearchHelpers.range_violations({"author": {"gte": "a"}}, _range_schema())
    assert any("not range-typed" in e for e in errors)


def test_malformed_range_key_is_rejected(fastapi_app) -> None:
    from backend.routers.search.helpers import SearchHelpers  # noqa: PLC0415

    errors = SearchHelpers.range_violations({"pages": {"between": 3}}, _range_schema())
    assert any("unsupported key" in e for e in errors)


def test_numeric_bounds_on_datetime_field_are_rejected(fastapi_app) -> None:
    from backend.routers.search.helpers import SearchHelpers  # noqa: PLC0415

    errors = SearchHelpers.range_violations({"published": {"gte": 2024}}, _range_schema())
    assert any("ISO-8601 datetime" in e for e in errors)


def test_datetime_bounds_on_numeric_field_are_rejected(fastapi_app) -> None:
    from backend.routers.search.helpers import SearchHelpers  # noqa: PLC0415

    errors = SearchHelpers.range_violations({"pages": {"gte": "2024-01-01"}}, _range_schema())
    assert any("numeric" in e for e in errors)


def test_scalar_and_list_filters_are_not_range_violations(fastapi_app) -> None:
    from backend.routers.search.helpers import SearchHelpers  # noqa: PLC0415

    errors = SearchHelpers.range_violations(
        {"author": "kafka", "pages": [1, 2, 3]}, _range_schema()
    )
    assert errors == []


def test_range_on_non_filterable_field_is_not_this_gates_concern(fastapi_app) -> None:
    from backend.routers.search.helpers import SearchHelpers  # noqa: PLC0415
    from shared_libs.public_models import FieldType  # noqa: PLC0415

    schema = [_typed_field("pages", FieldType.INTEGER, filterable=False)]
    assert SearchHelpers.range_violations({"pages": {"gte": 1}}, schema) == []


def test_range_violations_never_crashes_on_a_typeless_stand_in(fastapi_app) -> None:
    """A plain scalar/list filter must never make range_violations inspect a field's type (it runs
    on every search) — a stand-in schema carrying no field_type stays crash-free."""
    from backend.routers.search.helpers import SearchHelpers  # noqa: PLC0415

    schema = [SimpleNamespace(field_name="topic", filterable=True)]  # no field_type at all
    assert SearchHelpers.range_violations({"topic": "ai"}, schema) == []


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


# ---------------------- score_kind (F15 — score semantics) ---------------------- #
def test_score_kind_empty_blob_is_rrf_fusion(fastapi_app) -> None:
    from backend.routers.search.helpers import SearchHelpers  # noqa: PLC0415

    # An empty / None search blob is the stock default topology: hybrid retrieve, RRF fusion.
    assert SearchHelpers.score_kind(None) == "rrf_fusion"
    assert SearchHelpers.score_kind({}) == "rrf_fusion"


def test_score_kind_dbsf_when_retrieve_config_says_so(fastapi_app) -> None:
    from backend.routers.search.helpers import SearchHelpers  # noqa: PLC0415

    blob = {"nodes": [{"family": "retrieve", "kind": "hybrid", "config": {"fusion": "dbsf"}}]}
    assert SearchHelpers.score_kind(blob) == "dbsf_fusion"


def test_score_kind_cross_encoder_when_rerank_present(fastapi_app) -> None:
    from backend.routers.search.helpers import SearchHelpers  # noqa: PLC0415

    blob = {
        "nodes": [
            {"family": "retrieve", "kind": "hybrid", "config": {"fusion": "rrf"}},
            {"family": "rerank", "kind": "cross_encoder", "config": {}},
        ]
    }
    assert SearchHelpers.score_kind(blob) == "cross_encoder_rerank"
