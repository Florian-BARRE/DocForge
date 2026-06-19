# ====== Code Summary ======
# S2 EnrichConfig: figure enrichment stage configuration for the DocForge pipeline.
# Covers figure classification, OCR, and VLM enrichment — each as an
# independently-gated provider chain.
#
# LEAF CONSTRAINT: no module-level import of libs.capabilities / libs.data /
# libs.engine / libs.governance — all concrete-provider imports stay LAZY
# (inside model_validator bodies).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from libs.core.contracts.chain_gate_config import ChainGateConfig
from libs.core.contracts.pipeline_config._helpers import _lift_provider_to_chain
from libs.core.contracts.spec_utils import flatten_provider_spec as _flatten_provider_spec


class EnrichConfig(BaseModel):
    """
    S2 enrichment configuration — figure classifier + OCR chain + VLM (spec §4.3).

    The ``vlm`` provider selects the Vision-Language Model backend used for figure
    grounding, chart description, and diagram captioning.  Two backends are available:

    ``LocalVlmConfig`` (id="openai_compat") — local OpenAI-compatible server (vLLM, Ollama).
        No api_key required (can be omitted or set to any placeholder).
        Required params: ``base_url``, ``model``.  Optional: ``api_key``, ``max_tokens``.

    ``OpenAIVlmConfig`` (id="openai") — external cloud API (OpenAI, Mistral, OpenRouter, …).
        ``api_key`` is REQUIRED — raises at provider init if empty or missing.
        Required params: ``base_url``, ``api_key``, ``model``.
        Optional: ``max_tokens``, ``cost_per_call`` (float, USD; used for budget tracking).

    Attributes:
        chart_to_data (bool): Extract chart series into a structured data_table.
        max_budget_usd (float): Per-job spend cap in USD. 0.0 = no limit.
        classifier_chain (list[ClassifierConfig]): Ordered figure classifier chain; index 0
            is tried first.
        classifier_gate (ChainGateConfig): Escalation policy for the classifier chain.
        ocr_chain (list[OcrProviderConfig]): Ordered OCR escalation chain. Empty = no OCR.
        ocr_gate (ChainGateConfig): Escalation policy for the OCR chain.
        vlm_chain (list[VlmProviderConfig]): Ordered VLM providers; empty = VLM disabled.
        vlm_gate (ChainGateConfig): Escalation policy for the VLM chain.
    """

    chart_to_data: bool = False
    max_budget_usd: float = 0.0
    classifier_chain: list[Any] = Field(
        default_factory=list,
        description="Ordered figure classifier chain; index 0 is tried first.",
    )
    classifier_gate: ChainGateConfig = Field(
        default_factory=ChainGateConfig,
        description="Escalation policy for the classifier chain.",
    )
    ocr_chain: list[Any] = Field(
        default_factory=list,
        description="Ordered OCR providers; empty list disables OCR.",
    )
    ocr_gate: ChainGateConfig = Field(
        default_factory=lambda: ChainGateConfig(min_score=0.85),
        description="Escalation policy for the OCR chain (default min_score=0.85 preserves legacy threshold).",
    )
    vlm_chain: list[Any] = Field(
        default_factory=list,
        description="Ordered VLM providers; empty list disables VLM enrichment entirely.",
    )
    vlm_gate: ChainGateConfig = Field(
        default_factory=ChainGateConfig,
        description="Escalation policy for the VLM chain.",
    )

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        """
        Lift legacy single-provider fields to the new chain shape and flatten entries.

        Old shapes handled:
        - ``classifier: {...}``     → ``classifier_chain: [{...}]``
        - ``vlm: {...}`` (or None)  → ``vlm_chain: [{...}]`` or ``[]``
        - ``ocr_chain: [{id, params}]`` → flatten each entry to ``{id, ...}``
        """
        if not isinstance(v, dict):
            return v
        v = dict(v)
        v = _lift_provider_to_chain(v, chain_key="classifier_chain", provider_key="classifier")
        v = _lift_provider_to_chain(v, chain_key="vlm_chain", provider_key="vlm")
        if "ocr_chain" in v and isinstance(v["ocr_chain"], list):
            v["ocr_chain"] = [
                _flatten_provider_spec(item) if isinstance(item, dict) else item
                for item in v["ocr_chain"]
            ]
        return v

    @model_validator(mode="after")
    def _validate_and_default_enrich_chains(self) -> EnrichConfig:
        """
        Validate each chain field via discriminated unions, then apply defaults.

        For each chain (classifier_chain, ocr_chain, vlm_chain):
        - Dict items are coerced through the typed discriminated union; an unknown id
          raises ValidationError immediately (not at registry resolution time).
        - Already-typed instances are passed through unchanged.
        - Empty classifier_chain is defaulted to [LayoutLabelsConfig()].
        - Empty ocr_chain and vlm_chain stay empty (disabled by default).
        """
        # Lazy imports to preserve the leaf constraint.
        from typing import Annotated

        from pydantic import Field as _F
        from pydantic import TypeAdapter

        from libs.capabilities.classifier.local.layout_labels_config import LayoutLabelsConfig
        from libs.capabilities.classifier.local.vit_onnx_config import VitOnnxConfig
        from libs.capabilities.ocr.external.mistral_ocr_config import MistralOcrConfig
        from libs.capabilities.ocr.local.paddle_ocr_config import PaddleOcrConfig
        from libs.capabilities.vlm.external.openai_compat_config import OpenAIVlmConfig
        from libs.capabilities.vlm.local.openai_compat_config import LocalVlmConfig

        # 1. Validate classifier_chain items, then default if empty.
        classifier_union = Annotated[
            LayoutLabelsConfig | VitOnnxConfig,
            _F(discriminator="id"),
        ]
        classifier_adapter = TypeAdapter(classifier_union)
        if self.classifier_chain:
            coerced_classifier = [
                classifier_adapter.validate_python(item) if isinstance(item, dict) else item
                for item in self.classifier_chain
            ]
            object.__setattr__(self, "classifier_chain", coerced_classifier)
        else:
            object.__setattr__(self, "classifier_chain", [LayoutLabelsConfig()])

        # 2. Validate ocr_chain items (stays empty if no items provided).
        ocr_union = Annotated[
            PaddleOcrConfig | MistralOcrConfig,
            _F(discriminator="id"),
        ]
        ocr_adapter = TypeAdapter(ocr_union)
        if self.ocr_chain:
            coerced_ocr = [
                ocr_adapter.validate_python(item) if isinstance(item, dict) else item
                for item in self.ocr_chain
            ]
            object.__setattr__(self, "ocr_chain", coerced_ocr)

        # 3. Validate vlm_chain items (stays empty if no items provided).
        vlm_union = Annotated[
            LocalVlmConfig | OpenAIVlmConfig,
            _F(discriminator="id"),
        ]
        vlm_adapter = TypeAdapter(vlm_union)
        if self.vlm_chain:
            coerced_vlm = [
                vlm_adapter.validate_python(item) if isinstance(item, dict) else item
                for item in self.vlm_chain
            ]
            object.__setattr__(self, "vlm_chain", coerced_vlm)

        return self
