# ====== Code Summary ======
# Top-level PipelineConfig model and build_default_pipeline() factory.
#
# PipelineConfig is the per-collection / per-playground pipeline contract
# (spec §3, §6.1): it composes all stage configs (ParseConfig → EnrichConfig
# → ChunkConfig → ContextualizeConfig → EmbedConfig) into a single serialisable
# Pydantic document.
#
# build_default_pipeline() translates RUNTIME_CONFIG deployment env-vars into a
# fully-typed config; both entrypoint.py and worker.py call it instead of
# constructing providers directly.
#
# LEAF CONSTRAINT: no module-level import of libs.capabilities / libs.data /
# libs.engine / libs.governance — all concrete-provider imports stay LAZY
# (inside the function body of build_default_pipeline).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from libs.core.contracts.chain_gate_config import ChainGateConfig
from libs.core.contracts.pipeline_config._helpers import _redact
from libs.core.contracts.pipeline_config.chunk_config import ChunkConfig
from libs.core.contracts.pipeline_config.contextualize_config import ContextualizeConfig
from libs.core.contracts.pipeline_config.embed_config import EmbedConfig
from libs.core.contracts.pipeline_config.enrich_config import EnrichConfig
from libs.core.contracts.pipeline_config.parse_config import ParseConfig


class PipelineConfig(BaseModel):
    """
    The full per-collection / per-playground pipeline contract.

    Attributes:
        parse (ParseConfig): S1 parsing.
        enrich (EnrichConfig): S2 enrichment.
        chunk (ChunkConfig): S4 chunking + S5 contextualization.
        contextualize (ContextualizeConfig): S5 contextualization options.
        embed (EmbedConfig): S6 embedding + indexing.
    """

    parse: ParseConfig = Field(default_factory=ParseConfig)
    enrich: EnrichConfig = Field(default_factory=EnrichConfig)
    chunk: ChunkConfig = Field(default_factory=ChunkConfig)
    contextualize: ContextualizeConfig = Field(default_factory=ContextualizeConfig)
    embed: EmbedConfig = Field(default_factory=EmbedConfig)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> PipelineConfig:
        """
        Build a PipelineConfig from a (possibly empty/partial) JSON dict.

        An empty/None dict falls back to defaults; a partial dict fills the rest from defaults.

        Args:
            raw (dict | None): Serialized config (collection.pipeline jsonb or request body).

        Returns:
            PipelineConfig: Parsed config with defaults filled in.
        """
        if not raw:
            return cls()
        return cls.model_validate(raw)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain JSON-compatible dict (for collection.pipeline storage)."""
        return self.model_dump(mode="json")

    def redacted_dict(self) -> dict[str, Any]:
        """
        Serialize with all credential params masked — safe to echo to clients and logs.

        Returns:
            dict: The config with secret provider params replaced by "•••".
        """
        return _redact(self.model_dump(mode="json"))


def build_default_pipeline(cfg: Any) -> PipelineConfig:
    """
    Build the default PipelineConfig from RUNTIME_CONFIG deployment env vars.

    This is the single authoritative translation from env-var booleans to a
    typed discriminated-union config.  Both entrypoint.py and worker.py call
    this instead of direct provider instantiation.

    Args:
        cfg: RUNTIME_CONFIG instance with all deployment env vars.

    Returns:
        PipelineConfig: Fully typed config representing the deployment's default stack.
    """
    # Lazy imports — triggered only when this function is actually called (after providers
    # register themselves), not at module load time.  Preserves the leaf constraint.
    from libs.capabilities.classifier.local.layout_labels import LayoutLabelsConfig
    from libs.capabilities.classifier.local.vit_onnx import VitOnnxConfig
    from libs.capabilities.embed.local.config import TeiEmbedConfig
    from libs.capabilities.ocr.external.mistral_ocr import MistralOcrConfig
    from libs.capabilities.ocr.local.paddle_ocr import PaddleOcrConfig
    from libs.capabilities.parser.local.docling import DoclingConfig
    from libs.capabilities.vlm.local.openai_compat import LocalVlmConfig
    from libs.engine.stages.chunking.params import TokenBudgetConfig

    # 1. Parser chain
    parse_cfg = ParseConfig(
        chain=[DoclingConfig(use_gpu=getattr(cfg, "DOCLING_USE_GPU", False))]
    )

    # 2. Figure classifier chain
    classifier_type = getattr(cfg, "CLASSIFIER_TYPE", "layout_labels")
    if classifier_type == "vit_onnx":
        classifier_chain: list = [VitOnnxConfig(
            model_path=getattr(cfg, "CLASSIFIER_ONNX_MODEL_PATH", ""),
            use_gpu=getattr(cfg, "CLASSIFIER_USE_GPU", False),
        )]
    else:
        classifier_chain = [LayoutLabelsConfig()]

    # 3. OCR chain
    ocr_chain: list = []
    if getattr(cfg, "OCR_PADDLE_ENABLED", False):
        ocr_chain.append(PaddleOcrConfig(use_gpu=getattr(cfg, "OCR_PADDLE_USE_GPU", False)))
    if getattr(cfg, "MISTRAL_OCR_ENABLED", False):
        ocr_chain.append(MistralOcrConfig(
            api_key=getattr(cfg, "MISTRAL_OCR_API_KEY", ""),
            base_url=getattr(cfg, "MISTRAL_OCR_API_URL", "https://api.mistral.ai/v1"),
            model=getattr(cfg, "MISTRAL_OCR_MODEL", "mistral-ocr-latest"),
            timeout_s=getattr(cfg, "MISTRAL_OCR_TIMEOUT_S", 60),
        ))

    # 4. VLM chain (empty = disabled)
    vlm_chain: list = []
    if getattr(cfg, "VLM_ENABLED", False):
        vlm_chain.append(LocalVlmConfig(
            base_url=getattr(cfg, "VLM_API_BASE_URL", ""),
            api_key=getattr(cfg, "VLM_API_KEY", ""),
            model=getattr(cfg, "VLM_MODEL", ""),
            timeout_s=getattr(cfg, "VLM_TIMEOUT_S", 30),
            max_tokens=getattr(cfg, "VLM_MAX_TOKENS", 1024),
            cost_per_call=getattr(cfg, "VLM_COST_PER_CALL", 0.0),
        ))

    # OCR gate inherits the legacy threshold (default 0.85 if not present).
    ocr_threshold = float(getattr(cfg, "OCR_CONFIDENCE_THRESHOLD", 0.85))

    enrich_cfg = EnrichConfig(
        classifier_chain=classifier_chain,
        ocr_chain=ocr_chain,
        ocr_gate=ChainGateConfig(min_score=ocr_threshold),
        vlm_chain=vlm_chain,
        max_budget_usd=getattr(cfg, "ENRICH_MAX_BUDGET_USD", 0.0),
    )

    # 5. Chunking
    chunk_cfg = ChunkConfig(
        split_method=TokenBudgetConfig(
            max_tokens=getattr(cfg, "CHUNK_MAX_TOKENS", 512),
            overlap_blocks=getattr(cfg, "CHUNK_OVERLAP_BLOCKS", 0),
        )
    )

    # 6. Embedding chain
    embed_cfg = EmbedConfig(
        chain=[TeiEmbedConfig(
            base_url=getattr(cfg, "TEI_BASE_URL", "http://tei:8080"),
            batch_size=getattr(cfg, "TEI_BATCH_SIZE", 32),
        )]
    )

    return PipelineConfig(parse=parse_cfg, enrich=enrich_cfg, chunk=chunk_cfg, embed=embed_cfg)
