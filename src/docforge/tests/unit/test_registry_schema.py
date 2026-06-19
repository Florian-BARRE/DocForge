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
        # _params_from_model includes 'id' (no exclusion, unlike _params_from_instance).
        # SemanticConfig fields: id, embed, max_tokens, min_tokens, breakpoint_percentile.
        assert set(params) == {"id", "embed", "max_tokens", "min_tokens", "breakpoint_percentile"}
        bp = params["breakpoint_percentile"]
        assert bp["type"] == "int" and bp["min"] == 50 and bp["max"] == 99 and bp["default"] == 90
        assert params["max_tokens"]["type"] == "int"

    def test_adding_a_model_field_propagates(self) -> None:
        """A field added to the params model appears automatically (no hand list to update)."""
        names = {p["name"] for p in _params_from_model(SemanticParams)}
        # _params_from_model does NOT exclude 'id' (unlike _params_from_instance which skips it).
        # This explicit enumeration must be updated whenever SemanticConfig fields change —
        # that is the point: drift causes a loud failure here.
        assert names == {"id", "embed", "max_tokens", "min_tokens", "breakpoint_percentile"}
