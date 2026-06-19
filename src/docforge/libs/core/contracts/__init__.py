# ─────────────────── Registry (auto-registration API) ─────────────── #
from libs.core.contracts._registry import register, get_configs, build_union, auto_import

# ─────────────────── Gate Config ──────────────────────────────────── #
from libs.core.contracts.chain_gate_config import ChainGateConfig

# ─────────────────── Pipeline Contract ────────────────────────────── #
from libs.core.contracts.pipeline_config import (
    PipelineConfig,
    ParseConfig,
    EnrichConfig,
    ChunkConfig,
    ContextualizeConfig,
    EmbedConfig,
    AtomicConfig,
    HeadingRule,
    ProviderSpec,
    SplitMethodConfig,
    ParserConfig,
    ClassifierConfig,
    OcrProviderConfig,
    VlmProviderConfig,
    EmbedProviderConfig,
    SPLIT_METHODS,
    DEFAULT_HEADING_RULES,
    build_default_pipeline,
    _is_secret_key,
    _flatten_provider_spec,
)

# ─────────────────── Public API ───────────────────────────────────── #
__all__ = [
    # Registry
    "register",
    "get_configs",
    "build_union",
    "auto_import",
    # Gate
    "ChainGateConfig",
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
    "_flatten_provider_spec",
]
