# ====== Code Summary ======
# Drift-guard + derivation tests: the chunk split-method discovery schema must be GENERATED from
# the Pydantic params models / SPLIT_METHODS source of truth, never hand-maintained.
# Also contains regression tests for discriminator validation on pipeline chain fields.

import common_libs.pipeline.stages.s4_chunk as _chunking_pkg  # noqa: F401 — triggers @register("split_method")
import common_libs.providers.embed as _embed_pkg  # noqa: F401 — triggers @register("embed") decorators
import common_libs.providers.parser as _parser_pkg  # noqa: F401 — triggers @register("parser") decorators
import common_libs.providers.ocr as _ocr_pkg  # noqa: F401 — triggers @register("ocr") decorators
import common_libs.providers.classifier as _classifier_pkg  # noqa: F401 — triggers @register("classifier") decorators
import common_libs.providers.vlm as _vlm_pkg  # noqa: F401 — triggers @register("vlm") decorators

import pytest
from pydantic import ValidationError

from common_libs.config.pipeline import SPLIT_METHODS, PipelineConfig
from common_libs.pipeline.stages.s4_chunk import (
    SPLIT_METHOD_PARAMS,
    SemanticParams,
    TokenBudgetConfig,
)
from common_libs.config.pipeline._registry import get_configs
from common_libs.pipeline.assembly import _params_from_model


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
        from common_libs.pipeline.stages.s4_chunk.strategies.params import SemanticConfig
        available, note = SemanticConfig.availability(None)
        assert isinstance(available, bool)
        assert isinstance(note, str)


class TestParamsDerivation:
    def test_params_carry_type_bounds_and_defaults(self) -> None:
        """Param descriptors are derived from the model's JSON schema (type + ge/le + default)."""
        params = {p["name"]: p for p in _params_from_model(SemanticParams)}
        # _params_from_model keeps 'id' but SKIPS non-scalar fields: SemanticConfig.embed is a
        # nested EmbedProviderConfig (not a single scalar control) and must not surface.
        assert set(params) == {"id", "max_tokens", "min_tokens", "breakpoint_percentile"}
        assert "embed" not in params  # nested provider config — excluded, never "[object Object]"
        bp = params["breakpoint_percentile"]
        assert bp["type"] == "int" and bp["min"] == 50 and bp["max"] == 99 and bp["default"] == 90
        assert params["max_tokens"]["type"] == "int"

    def test_adding_a_model_field_propagates(self) -> None:
        """A field added to the params model appears automatically (no hand list to update)."""
        names = {p["name"] for p in _params_from_model(SemanticParams)}
        # Scalar fields surface automatically; the nested 'embed' provider config is excluded.
        # This explicit enumeration must be updated whenever SemanticConfig's SCALAR fields change —
        # that is the point: drift causes a loud failure here.
        assert names == {"id", "max_tokens", "min_tokens", "breakpoint_percentile"}


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
        assert cfg.embed.chain[0].id == "bge_server"  # defaulted to BgeServerEmbedConfig

    def test_valid_known_ids_pass_through(self) -> None:
        """Known provider ids must parse cleanly without raising."""
        cfg = PipelineConfig.model_validate({
            "embed": {"chain": [{"id": "bge_server", "base_url": "http://bge_server:80"}]},
            "parse": {"chain": [{"id": "docling"}]},
        })
        assert cfg.embed.chain[0].id == "bge_server"
        assert cfg.parse.chain[0].id == "docling"

    def test_legacy_tei_embed_id_normalizes_to_bge_server(self) -> None:
        """
        A stored pipeline referencing the removed ``tei`` embed choice must still load and be
        rewritten to ``bge_server`` (the off-the-shelf TEI image was replaced by bge_server,
        which speaks the same TEI HTTP contract). Compatible fields are carried over; bge_server's
        extra ``timeout_s`` falls back to its default.
        """
        cfg = PipelineConfig.model_validate({
            "embed": {"chain": [{
                "id": "tei",
                "base_url": "http://bge_server:80",
                "model": "BAAI/bge-m3",
                "batch_size": 16,
                "embed_sparse": True,
            }]},
        })
        provider = cfg.embed.chain[0]
        assert provider.id == "bge_server"            # legacy id rewritten
        assert provider.base_url == "http://bge_server:80"  # compatible field carried over
        assert provider.batch_size == 16               # compatible field carried over
        assert provider.embed_sparse is True           # compatible field carried over
        assert provider.timeout_s == 180               # new field falls back to bge_server default


# ─── Device-knob removal backward-compat ─────────────────────────────────────────
# `use_gpu` was removed from the docling / paddle_ocr / vit_onnx configs (GPU is a deployment
# decision resolved from the *_USE_GPU env, never a per-collection field). A collection whose
# stored pipeline JSON still carries a stale `use_gpu` MUST still load — the key is dropped, never
# resurfaced. This locks in the `extra="ignore"` guarantee on those three config models.


class TestDeviceKnobBackwardCompat:
    """Stored configs carrying a stale `use_gpu` load cleanly and never echo the key back."""

    def test_stale_use_gpu_is_dropped_across_providers(self) -> None:
        """A legacy `use_gpu` on docling/paddle/vit chains loads and is stripped from the dump."""
        cfg = PipelineConfig.model_validate({
            "parse": {"chain": [{"id": "docling", "use_gpu": True}]},
            "enrich": {
                "ocr_chain": [{"id": "paddle_ocr", "use_gpu": True}],
                "classifier_chain": [{"id": "vit_onnx", "use_gpu": True, "model_path": "/m.onnx"}],
            },
        })
        # 1. The stale key never survives validation (it is off the schema).
        assert "use_gpu" not in cfg.parse.chain[0].model_dump()
        assert "use_gpu" not in cfg.enrich.ocr_chain[0].model_dump()
        assert "use_gpu" not in cfg.enrich.classifier_chain[0].model_dump()
        # 2. Legitimate per-collection fields are preserved.
        assert cfg.enrich.classifier_chain[0].model_path == "/m.onnx"

    def test_use_gpu_absent_from_provider_schemas(self) -> None:
        """`use_gpu` must not appear in the JSON schema of any device-bearing provider config."""
        from common_libs.providers.parser.docling import DoclingConfig
        from common_libs.providers.ocr.paddle.config import PaddleOcrConfig
        from common_libs.providers.classifier.vit_onnx.config import VitOnnxConfig

        for model in (DoclingConfig, PaddleOcrConfig, VitOnnxConfig):
            assert "use_gpu" not in model.model_json_schema()["properties"]
