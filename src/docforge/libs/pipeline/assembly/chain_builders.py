# ====== Code Summary ======
# ChainBuilderHelpers — static builders that turn a list of typed ProviderSpec configs into a
# concrete Chain[T, R] for each stage category (parser / classifier / OCR / VLM / embed).
# Each builder merges deployment defaults into every spec, validates provider availability
# (credential/endpoint/model presence), and wraps the instantiated providers in a Chain.
# Extracted from ProviderRegistry to keep the resolution core under the line budget.

# ====== Standard Library Imports ======
from __future__ import annotations

import os
from typing import Any

# ====== Third-Party Library Imports ======
from libs.capabilities.chain import Chain
from libs.capabilities.chain_gate import ChainGate, ChainGateConfig
from libs.capabilities.classifier.local.vit_onnx_config import VitOnnxConfig
from libs.capabilities.ocr.external.mistral_ocr_config import MistralOcrConfig
from libs.capabilities.ocr.local.paddle_ocr_config import PaddleOcrConfig
from libs.capabilities.parser.local.docling import DoclingConfig
from libs.capabilities.vlm.external.openai_compat_config import OpenAIVlmConfig
from libs.capabilities.vlm.local.openai_compat_config import LocalVlmConfig

# ====== Internal Project Imports ======
from libs.core.contracts.pipeline_config import ProviderSpec

# ====== Local Project Imports ======
from .availability import ProviderUnavailableError


class ChainBuilderHelpers:
    """
    Static chain builders shared by ProviderRegistry.

    Each ``build_*`` classmethod instantiates the providers declared in ``specs`` (in order),
    merging deployment defaults from ``cfg`` and raising ProviderUnavailableError when a knob
    cannot be honored.  All builders are stateless apart from the passed-in ``cfg``.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("ChainBuilderHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def build_parser_chain(
        cfg: Any,
        specs: list[ProviderSpec],
        gate_cfg: ChainGateConfig,
    ) -> Chain[Any, Any]:
        """
        Instantiate the parser providers in declaration order and wrap them in a Chain.

        Args:
            cfg (Any): RUNTIME_CONFIG — deployment defaults merged into each spec.
            specs (list[ProviderSpec]): Typed parser configs (currently only DoclingConfig).
            gate_cfg (ChainGateConfig): Escalation policy applied after each attempt.

        Returns:
            Chain[ParserProvider, DocumentIR]: Wired parser chain.

        Raises:
            ProviderUnavailableError: When a requested parser cannot be instantiated.
        """
        if not specs:
            raise ProviderUnavailableError(
                "parse", "none", "At least one parser must be configured.",
            )
        built: list[Any] = []
        for spec in specs:
            if not isinstance(spec, DoclingConfig):
                raise ProviderUnavailableError(
                    "parse", getattr(spec, "id", str(spec)),
                    "Only the Docling backend is installed in this deployment.",
                )
            merged = spec.merge_defaults(cfg)
            built.append(merged.build())
        return Chain(stage="parse", providers=built, gate=ChainGate(gate_cfg))

    @staticmethod
    def build_classifier_chain(
        cfg: Any,
        specs: list[ProviderSpec],
        gate_cfg: ChainGateConfig,
    ) -> Chain[Any, Any]:
        """Build the figure-classifier chain (ViT and/or LayoutLabels)."""
        if not specs:
            raise ProviderUnavailableError(
                "classifier", "none", "At least one classifier must be configured.",
            )
        built: list[Any] = []
        for spec in specs:
            merged = spec.merge_defaults(cfg)
            if isinstance(merged, VitOnnxConfig):
                if not os.path.exists(merged.model_path):
                    raise ProviderUnavailableError(
                        "classifier", "vit_onnx",
                        f"ONNX model not found at {merged.model_path}.",
                    )
            built.append(merged.build())
        return Chain(stage="classifier", providers=built, gate=ChainGate(gate_cfg))

    @staticmethod
    def build_ocr_chain(
        cfg: Any,
        specs: list[ProviderSpec],
        gate_cfg: ChainGateConfig,
    ) -> Chain[Any, Any] | None:
        """
        Build the OCR escalation chain.

        Returns None when no OCR providers are configured — the caller must guard against
        that case and skip OCR routing.
        """
        if not specs:
            return None
        built: list[Any] = []
        for spec in specs:
            merged = spec.merge_defaults(cfg)
            if isinstance(merged, PaddleOcrConfig):
                try:
                    import paddleocr  # noqa: F401
                except Exception:
                    raise ProviderUnavailableError(
                        "ocr", "paddle_ocr", "paddleocr package is not installed.",
                    )
            elif isinstance(merged, MistralOcrConfig):
                if not merged.api_key:
                    raise ProviderUnavailableError(
                        "ocr", "mistral_ocr",
                        "No API key — fill it in the playground or set MISTRAL_OCR_API_KEY.",
                    )
            else:
                raise ProviderUnavailableError(
                    "ocr", getattr(merged, "id", str(merged)), "Unknown OCR provider id.",
                )
            built.append(merged.build())
        return Chain(stage="ocr", providers=built, gate=ChainGate(gate_cfg))

    @staticmethod
    def build_vlm_chain(
        cfg: Any,
        specs: list[ProviderSpec],
        gate_cfg: ChainGateConfig,
    ) -> Chain[Any, Any] | None:
        """
        Build the VLM escalation chain.

        Returns None when ``specs`` is empty — disables VLM enrichment entirely.
        """
        if not specs:
            return None
        built: list[Any] = []
        for spec in specs:
            merged = spec.merge_defaults(cfg)
            if isinstance(merged, LocalVlmConfig):
                if not merged.base_url:
                    raise ProviderUnavailableError(
                        "vlm", "openai_compat", "No VLM base URL configured.",
                    )
            elif isinstance(merged, OpenAIVlmConfig):
                if not merged.base_url:
                    raise ProviderUnavailableError(
                        "vlm", "openai", "No VLM base URL configured.",
                    )
                if not merged.api_key:
                    raise ProviderUnavailableError(
                        "vlm", "openai",
                        "No API key — fill it in the playground or set VLM_API_KEY.",
                    )
            else:
                raise ProviderUnavailableError(
                    "vlm", getattr(merged, "id", str(merged)),
                    "Unknown VLM provider id. Valid ids: 'openai_compat' (local), 'openai' (cloud).",
                )
            built.append(merged.build())
        return Chain(stage="vlm", providers=built, gate=ChainGate(gate_cfg))

    @staticmethod
    def build_embed_chain(
        cfg: Any,
        specs: list[ProviderSpec],
        gate_cfg: ChainGateConfig,
    ) -> Chain[Any, Any]:
        """Build the S6 embed chain from typed EmbedProviderConfig specs."""
        if not specs:
            raise ProviderUnavailableError(
                "embed", "none", "At least one embed provider must be configured.",
            )
        built: list[Any] = []
        for spec in specs:
            merged = spec.merge_defaults(cfg)
            built.append(merged.build())
        return Chain(stage="embed", providers=built, gate=ChainGate(gate_cfg))


# ------------------- Public API ------------------- #
__all__ = ["ChainBuilderHelpers"]
