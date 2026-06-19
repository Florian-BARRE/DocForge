# ====== Code Summary ======
# Drift-guard + derivation tests: the chunk split-method discovery schema must be GENERATED from
# the Pydantic params models / SPLIT_METHODS source of truth, never hand-maintained.

import pipeline.stages.chunking as _chunking_pkg  # noqa: F401 — triggers @register("split_method")

from pipeline.pipeline_config import SPLIT_METHODS
from pipeline.stages.chunking import (
    SPLIT_METHOD_PARAMS,
    SemanticParams,
    TokenBudgetConfig,
)
from providers._registry import get_configs
from providers.registry import _params_from_model


class TestSplitMethodCatalogDrift:
    def test_catalog_matches_source_of_truth(self) -> None:
        """The params catalog must cover exactly the declared SPLIT_METHODS — no drift."""
        assert set(SPLIT_METHOD_PARAMS.keys()) == set(SPLIT_METHODS)

    def test_registered_split_methods_match_catalog(self) -> None:
        """The auto-registry must cover exactly the same ids as SPLIT_METHOD_PARAMS — no drift."""
        registered_ids = set(get_configs("split_method").keys())
        assert registered_ids == set(SPLIT_METHOD_PARAMS.keys())

    def test_split_method_provider_order_matches_catalog(self) -> None:
        """Provider ids from the auto-registry follow SPLIT_METHOD_PARAMS insertion order."""
        registered = list(get_configs("split_method").keys())
        assert registered == list(SPLIT_METHOD_PARAMS.keys())

    def test_token_budget_always_available(self) -> None:
        """token_budget has no external dependency and must always report available=True."""
        available, _ = TokenBudgetConfig.availability(None)
        assert available is True

    def test_semantic_availability_call_succeeds(self) -> None:
        """semantic.availability() must return a (bool, str) tuple without raising."""
        from pipeline.stages.chunking.params import SemanticConfig
        available, note = SemanticConfig.availability(None)
        assert isinstance(available, bool)
        assert isinstance(note, str)


class TestParamsDerivation:
    def test_params_carry_type_bounds_and_defaults(self) -> None:
        """Param descriptors are derived from the model's JSON schema (type + ge/le + default)."""
        params = {p["name"]: p for p in _params_from_model(SemanticParams)}
        # SemanticConfig has: id (excluded by _params_from_model), embed, max_tokens,
        # min_tokens, breakpoint_percentile — base_url is no longer a direct field.
        assert "max_tokens" in params
        assert "min_tokens" in params
        assert "breakpoint_percentile" in params
        bp = params["breakpoint_percentile"]
        assert bp["type"] == "int" and bp["min"] == 50 and bp["max"] == 99 and bp["default"] == 90
        assert params["max_tokens"]["type"] == "int"

    def test_adding_a_model_field_propagates(self) -> None:
        """A field added to the params model appears automatically (no hand list to update)."""
        names = {p["name"] for p in _params_from_model(SemanticParams)}
        # _params_from_model reads JSON schema 'properties' — 'id' is excluded because
        # _params_from_instance skips it; _params_from_model does not skip it, so we
        # assert that the derived set matches the model fields (including 'id').
        assert names == set(SemanticParams.model_fields.keys())
