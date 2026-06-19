# ─────────────────── Registry (auto-registration API) ─────────────── #
from libs.config.pipeline._registry import auto_import, build_union, get_configs, register

# ─────────────────── Gate Config ──────────────────────────────────── #
from libs.config.pipeline.chain_gate_config import ChainGateConfig

# ─────────────────── Pipeline Contract ────────────────────────────── #
from libs.config.pipeline import (
    DEFAULT_HEADING_RULES,
    SPLIT_METHODS,
    AtomicConfig,
    ChunkConfig,
    ClassifierConfig,
    ContextualizeConfig,
    EmbedConfig,
    EmbedProviderConfig,
    EnrichConfig,
    HeadingRule,
    OcrProviderConfig,
    ParseConfig,
    ParserConfig,
    PipelineConfig,
    ProviderSpec,
    SplitMethodConfig,
    VlmProviderConfig,
    _is_secret_key,
    build_default_pipeline,
)

# ─────────────────── Shared spec helper ───────────────────────────── #
from libs.config.pipeline.spec_utils import flatten_provider_spec

# ─────────────────── Public API ───────────────────────────────────── #
__all__ = [
    # Registry
    "register",
    "get_configs",
    "build_union",
    "auto_import",
    # Gate
    "ChainGateConfig",
    # Spec helper
    "flatten_provider_spec",
    # Pipeline contract
    "PipelineConfig",
    "ParseConfig",
    "EnrichConfig",
    "ChunkConfig",
    "ContextualizeConfig",
    "EmbedConfig",
    "AtomicConfig",
    "HeadingRule",
    "ProviderSpec",
    "SplitMethodConfig",
    "ParserConfig",
    "ClassifierConfig",
    "OcrProviderConfig",
    "VlmProviderConfig",
    "EmbedProviderConfig",
    "SPLIT_METHODS",
    "DEFAULT_HEADING_RULES",
    "build_default_pipeline",
    "_is_secret_key",
]
