# ====== Code Summary ======
# Drift-guard + derivation tests: the chunk split-method discovery schema must be GENERATED from
# the Pydantic params models / SPLIT_METHODS source of truth, never hand-maintained.

from pipeline.pipeline_config import SPLIT_METHODS
from pipeline.stages.chunking import (
    SPLIT_METHOD_PARAMS,
    SemanticParams,
)
from providers.registry import _chunk_split_providers, _params_from_model


class TestSplitMethodCatalogDrift:
    def test_catalog_matches_source_of_truth(self) -> None:
        """The params catalog must cover exactly the declared SPLIT_METHODS — no drift."""
        assert set(SPLIT_METHOD_PARAMS.keys()) == set(SPLIT_METHODS)

    def test_describe_providers_derived_from_catalog(self) -> None:
        """describe_stages' split options come from the catalog (ids + order)."""
        providers = _chunk_split_providers(tei_ok=True, tei_url="http://tei:8080")
        assert [p["id"] for p in providers] == list(SPLIT_METHOD_PARAMS.keys())
        # token_budget is the default, semantic depends on TEI availability
        by_id = {p["id"]: p for p in providers}
        assert by_id["token_budget"]["default"] is True
        assert by_id["semantic"]["available"] is True

    def test_semantic_unavailable_when_tei_down(self) -> None:
        providers = _chunk_split_providers(tei_ok=False, tei_url="http://tei:8080")
        semantic = next(p for p in providers if p["id"] == "semantic")
        assert semantic["available"] is False
        assert semantic["selectable"] is True  # URL is still fillable on the fly
        # base_url default is filled from the deployment TEI
        base_url = next(pr for pr in semantic["params"] if pr["name"] == "base_url")
        assert base_url["default"] == "http://tei:8080"


class TestParamsDerivation:
    def test_params_carry_type_bounds_and_defaults(self) -> None:
        """Param descriptors are derived from the model's JSON schema (type + ge/le + default)."""
        params = {p["name"]: p for p in _params_from_model(SemanticParams)}
        assert set(params) == {"max_tokens", "min_tokens", "breakpoint_percentile", "base_url"}
        bp = params["breakpoint_percentile"]
        assert bp["type"] == "int" and bp["min"] == 50 and bp["max"] == 99 and bp["default"] == 90
        assert params["base_url"]["type"] == "str"

    def test_adding_a_model_field_propagates(self) -> None:
        """A field added to the params model appears automatically (no hand list to update)."""
        names = {p["name"] for p in _params_from_model(SemanticParams)}
        assert names == set(SemanticParams.model_fields.keys())
