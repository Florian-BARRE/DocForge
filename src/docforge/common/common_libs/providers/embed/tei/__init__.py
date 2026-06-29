# ------------------- Config (triggers @register decorator) ------------------- #
from .config import TeiEmbedConfig

# NOTE: the runtime TeiEmbedProvider moved to the pipeline brick
# common_libs.pipeline.bricks.providers.embed (P1b inc-4b config/runtime split).

# ------------------- Public API ------------------- #
__all__ = [
    "TeiEmbedConfig",
]
