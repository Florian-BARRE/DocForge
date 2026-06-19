# ====== Code Summary ======
# Drift-guard + derivation tests: the chunk split-method discovery schema must be GENERATED from
# the Pydantic params models / SPLIT_METHODS source of truth, never hand-maintained.
# Also contains regression tests for discriminator validation on pipeline chain fields.

import libs.pipeline.stages.s4_chunk as _chunking_pkg  # noqa: F401 — triggers @register("split_method")
import libs.providers.embed as _embed_pkg  # noqa: F401 — triggers @register("embed") decorators
import libs.providers.parser as _parser_pkg  # noqa: F401 — triggers @register("parser") decorators
import libs.providers.ocr as _ocr_pkg  # noqa: F401 — triggers @register("ocr") decorators
import libs.providers.classifier as _classifier_pkg  # noqa: F401 — triggers @register("classifier") decorators
import libs.providers.vlm as _vlm_pkg  # noqa: F401 — triggers @register("vlm") decorators

import pytest
from pydantic import ValidationError

from libs.config.pipeline import SPLIT_METHODS, PipelineConfig
from libs.pipeline.stages.s4_chunk import (
    SPLIT_METHOD_PARAMS,
    SemanticParams,
    TokenBudgetConfig,
)
from libs.config.pipeline._registry import get_configs
from libs.pipeline.assembly import _params_from_model


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
        from libs.pipeline.stages.s4_chunk.strategies.params import SemanticConfig
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


# ─── Discriminator validation regression ─────────────────────────────────────────
# Regression guard: an unknown provider id in a chain field must raise ValidationError
# at PipelineConfig.model_validate() time — NOT later at registry resolution.
# This was broken when the typed discriminated-union aliases were replaced with Any
# during the contracts extraction refactor.


class TestChainDiscriminatorValidation:
    """Chain fields must reject unknown provider ids at parse time, not registry time."""

    def test_embed_chain_rejects_unknown_id(self) -> None:
        """An unknown id in embed.chain must raise ValidationError immediately."""
        with pytest.raises(ValidationError):
            PipelineConfig.model_validate({
                "embed": {"chain": [{"id": "nope"}]}
            })

    def test_parse_chain_rejects_unknown_id(self) -> None:
        """An unknown id in parse.chain must raise ValidationError immediately."""
        with pytest.raises(ValidationError):
            PipelineConfig.model_validate({
                "parse": {"chain": [{"id": "does_not_exist"}]}
            })

    def test_ocr_chain_rejects_unknown_id(self) -> None:
        """An unknown id in enrich.ocr_chain must raise ValidationError immediately."""
        with pytest.raises(ValidationError):
            PipelineConfig.model_validate({
                "enrich": {"ocr_chain": [{"id": "bad_ocr"}]}
            })

    def test_classifier_chain_rejects_unknown_id(self) -> None:
        """An unknown id in enrich.classifier_chain must raise ValidationError immediately."""
        with pytest.raises(ValidationError):
            PipelineConfig.model_validate({
                "enrich": {"classifier_chain": [{"id": "not_a_classifier"}]}
            })

    def test_vlm_chain_rejects_unknown_id(self) -> None:
        """An unknown id in enrich.vlm_chain must raise ValidationError immediately."""
        with pytest.raises(ValidationError):
            PipelineConfig.model_validate({
                "enrich": {"vlm_chain": [{"id": "bad_vlm"}]}
            })

    def test_empty_chains_stay_valid(self) -> None:
        """Empty chains must remain valid — only invalid ids should be rejected."""
        cfg = PipelineConfig.model_validate({
            "parse": {"chain": []},
            "enrich": {"ocr_chain": [], "classifier_chain": [], "vlm_chain": []},
            "embed": {"chain": []},
        })
        # Empty chains get defaults filled in by the model validators.
        assert cfg.parse.chain  # defaulted to DoclingConfig
        assert cfg.embed.chain  # defaulted to TeiEmbedConfig

    def test_valid_known_ids_pass_through(self) -> None:
        """Known provider ids must parse cleanly without raising."""
        cfg = PipelineConfig.model_validate({
            "embed": {"chain": [{"id": "tei", "base_url": "http://tei:8080"}]},
            "parse": {"chain": [{"id": "docling"}]},
        })
        assert cfg.embed.chain[0].id == "tei"
        assert cfg.parse.chain[0].id == "docling"
