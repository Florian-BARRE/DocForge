# ─────────────────── Registry (auto-registration API) ─────────────── #
from ._registry import auto_import, build_union, get_configs, register

# ─────────────────── Gate Config ──────────────────────────────────── #
from .chain_gate_config import ChainGateConfig

# ─────────────────── Type Aliases & Constants ──────────────────────── #
from ._type_aliases import (
    DEFAULT_HEADING_RULES,
    SPLIT_METHODS,
    ClassifierConfig,
    EmbedProviderConfig,
    OcrProviderConfig,
    ParserConfig,
    ProviderSpec,
    SplitMethodConfig,
    VlmProviderConfig,
)

# ─────────────────── Internal Helpers ─────────────────────────────── #
from ._helpers import _is_secret_key

# ─────────────────── Stage Configs ────────────────────────────────── #
from .stages.chunk_config import ChunkConfig
from .stages.contextualize_config import ContextualizeConfig
from .stages.embed_config import EmbedConfig
from .stages.enrich_config import EnrichConfig
from .stages.heading_rule import AtomicConfig, HeadingRule
from .stages.parse_config import ParseConfig

# ─────────────────── Top-level Pipeline ───────────────────────────── #
from .pipeline import PipelineConfig, build_default_pipeline

# ─────────────────── Shared spec helper ───────────────────────────── #
from .spec_utils import flatten_provider_spec

# ─────────────────── Public API ───────────────────────────────────── #
__all__ = [
    "register",
    "get_configs",
    "build_union",
    "auto_import",
    "ChainGateConfig",
    "ParserConfig",
    "ClassifierConfig",
    "OcrProviderConfig",
    "VlmProviderConfig",
    "EmbedProviderConfig",
    "SplitMethodConfig",
    "ProviderSpec",
    "SPLIT_METHODS",
    "DEFAULT_HEADING_RULES",
    "_is_secret_key",
    "ParseConfig",
    "EnrichConfig",
    "HeadingRule",
    "AtomicConfig",
    "ChunkConfig",
    "ContextualizeConfig",
    "EmbedConfig",
    "PipelineConfig",
    "build_default_pipeline",
    "flatten_provider_spec",
]
