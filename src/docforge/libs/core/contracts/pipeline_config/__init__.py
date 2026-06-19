# ─────────────────── Type Aliases & ProviderSpec ──────────────────── #
# ─────────────────── Internal Helpers (re-exported for registry.py) ── #
from libs.core.contracts.pipeline_config._helpers import _is_secret_key
from libs.core.contracts.pipeline_config._type_aliases import (
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

# ─────────────────── S4 + S5 + S6 Stage Configs ───────────────────── #
from libs.core.contracts.pipeline_config.chunk_config import ChunkConfig
from libs.core.contracts.pipeline_config.contextualize_config import ContextualizeConfig
from libs.core.contracts.pipeline_config.embed_config import EmbedConfig
from libs.core.contracts.pipeline_config.enrich_config import EnrichConfig

# ─────────────────── S4 Supporting Models ─────────────────────────── #
from libs.core.contracts.pipeline_config.heading_rule import AtomicConfig, HeadingRule

# ─────────────────── S1 + S2 Stage Configs ────────────────────────── #
from libs.core.contracts.pipeline_config.parse_config import ParseConfig

# ─────────────────── Top-level Pipeline ───────────────────────────── #
from libs.core.contracts.pipeline_config.pipeline import (
    PipelineConfig,
    build_default_pipeline,
)

# ─────────────────── Public API ───────────────────────────────────── #
__all__ = [
    # Type aliases
    "ParserConfig",
    "ClassifierConfig",
    "OcrProviderConfig",
    "VlmProviderConfig",
    "EmbedProviderConfig",
    "SplitMethodConfig",
    # Backward-compat model
    "ProviderSpec",
    # Constants
    "SPLIT_METHODS",
    "DEFAULT_HEADING_RULES",
    # Internal helper (used by registry.py)
    "_is_secret_key",
    # S1 + S2
    "ParseConfig",
    "EnrichConfig",
    # S4 + S5 + S6
    "HeadingRule",
    "AtomicConfig",
    "ChunkConfig",
    "ContextualizeConfig",
    "EmbedConfig",
    # Top-level
    "PipelineConfig",
    "build_default_pipeline",
]
