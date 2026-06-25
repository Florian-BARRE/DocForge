# ====== Code Summary ======
# Unit tests for the CHUNK-2 failure-policy model on the gate config + per-stage defaults.
# Covers: ChainGateConfig new fields + backward-compat (old gate without the fields loads),
# and the per-stage gate defaults (parse/embed = raise, enrich classifier/ocr/vlm = continue,
# ocr keeps min_score=0.85).

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Internal Project Imports ======
from common_libs.config.pipeline.chain_gate_config import ChainGateConfig
from common_libs.config.pipeline.stages.embed_config import EmbedConfig
from common_libs.config.pipeline.stages.enrich_config import EnrichConfig
from common_libs.config.pipeline.stages.parse_config import ParseConfig


class TestChainGateConfigFields:
    """The two new fields exist with the resolved defaults and validate their literals."""

    def test_defaults(self) -> None:
        gate = ChainGateConfig()
        assert gate.failure_policy == "raise"
        assert gate.on_degraded == "empty"

    def test_explicit_continue(self) -> None:
        gate = ChainGateConfig(failure_policy="continue", on_degraded="best_effort")
        assert gate.failure_policy == "continue"
        assert gate.on_degraded == "best_effort"

    def test_backward_compat_old_gate_without_new_fields_loads(self) -> None:
        """A gate serialized before the policy fields existed still loads (defaults applied)."""
        gate = ChainGateConfig.model_validate({"min_score": 0.6, "max_duration_ms": 2000})
        assert gate.min_score == 0.6
        assert gate.max_duration_ms == 2000
        assert gate.failure_policy == "raise"
        assert gate.on_degraded == "empty"

    def test_extra_ignore_drops_removed_max_cost_usd(self) -> None:
        """A since-removed knob (max_cost_usd) is ignored rather than raising (extra='ignore')."""
        gate = ChainGateConfig.model_validate({"min_score": 0.5, "max_cost_usd": 1.0})
        assert gate.min_score == 0.5
        assert not hasattr(gate, "max_cost_usd")


class TestPerStageGateDefaults:
    """Per-stage gate failure_policy defaults match the resolved design table."""

    def test_parse_defaults_to_raise(self) -> None:
        assert ParseConfig().gate.failure_policy == "raise"

    def test_embed_defaults_to_raise(self) -> None:
        assert EmbedConfig().gate.failure_policy == "raise"

    def test_enrich_classifier_defaults_to_continue(self) -> None:
        assert EnrichConfig().classifier_gate.failure_policy == "continue"

    def test_enrich_vlm_defaults_to_continue(self) -> None:
        assert EnrichConfig().vlm_gate.failure_policy == "continue"

    def test_enrich_ocr_defaults_to_continue_and_keeps_min_score(self) -> None:
        ocr_gate = EnrichConfig().ocr_gate
        assert ocr_gate.failure_policy == "continue"
        assert ocr_gate.min_score == 0.85

    def test_any_stage_may_be_set_to_either_policy(self) -> None:
        """No raise-only restriction: parse may be set to continue, enrich to raise (expert choice)."""
        parse = ParseConfig.model_validate({"gate": {"failure_policy": "continue"}})
        assert parse.gate.failure_policy == "continue"
        enrich = EnrichConfig.model_validate({"ocr_gate": {"failure_policy": "raise"}})
        assert enrich.ocr_gate.failure_policy == "raise"
