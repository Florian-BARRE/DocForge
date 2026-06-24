# ====== Code Summary ======
# Top-level PipelineConfig model and build_default_pipeline() factory.
#
# PipelineConfig is the per-collection / per-playground pipeline contract
# (spec Â§3, Â§6.1): it composes all stage configs (ParseConfig â†’ EnrichConfig
# â†’ ChunkConfig â†’ ContextualizeConfig â†’ EmbedConfig) into a single serialisable
# Pydantic document.
#
# build_default_pipeline() translates RUNTIME_CONFIG deployment env-vars into a
# fully-typed config; both entrypoint.py and worker.py call it instead of
# constructing providers directly.
#
# LEAF CONSTRAINT: no module-level import of libs.providers / libs.data /
# libs.pipeline / libs.config â€” all concrete-provider imports stay LAZY
# (inside the function body of build_default_pipeline).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from common_libs.config.pipeline.chain_gate_config import ChainGateConfig
from common_libs.config.pipeline._helpers import _redact
from common_libs.config.pipeline.stages.chunk_config import ChunkConfig
from common_libs.config.pipeline.stages.contextualize_config import ContextualizeConfig
from common_libs.config.pipeline.stages.embed_config import EmbedConfig
from common_libs.config.pipeline.stages.enrich_config import EnrichConfig
from common_libs.config.pipeline.stages.parse_config import ParseConfig
from common_libs.config.pipeline.stages.search_config import SearchConfig


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
    search: SearchConfig = Field(default_factory=SearchConfig)

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
        Serialize with all credential params masked â€” safe to echo to clients and logs.

        Returns:
            dict: The config with secret provider params replaced by "â€¢â€¢â€¢".
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
    # Lazy imports â€” triggered only when this function is actually called (after providers
    # register themselves), not at module load time.  Preserves the leaf constraint.
    from common_libs.providers.classifier.layout_labels.config import LayoutLabelsConfig
    from common_libs.providers.embed.tei.config import TeiEmbedConfig
    from common_libs.providers.parser.docling import DoclingConfig
    from common_libs.pipeline.stages.s4_chunk.strategies.params import TokenBudgetConfig

    # 1. Parser chain
    parse_cfg = ParseConfig(
        chain=[DoclingConfig(use_gpu=getattr(cfg, "DOCLING_USE_GPU", False))]
    )

    # 2. Figure classifier chain
    # Default deployment stack uses the heuristic layout-labels classifier; a per-collection
    # config swaps in vit_onnx (with its own model_path / use_gpu) when needed.
    classifier_chain: list = [LayoutLabelsConfig()]

    # 3. OCR chain — empty by default; OCR providers are opted in per-collection.
    ocr_chain: list = []

    # 4. VLM chain — empty by default (disabled); VLM is opted in per-collection.
    vlm_chain: list = []

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
    # base_url / batch_size are per-collection — TeiEmbedConfig structural defaults apply here.
    embed_cfg = EmbedConfig(chain=[TeiEmbedConfig()])

    return PipelineConfig(parse=parse_cfg, enrich=enrich_cfg, chunk=chunk_cfg, embed=embed_cfg)

