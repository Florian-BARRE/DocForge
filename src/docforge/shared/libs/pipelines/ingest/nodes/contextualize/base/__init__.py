# ---------------------- Shared contextualizer contract ---------------------- #
from .config import DEFAULT_SITUATE_PROMPT, BaseContextualizerConfig
from .enums import DocumentScope, OnChunkError
from .helpers import ContextualizeViewHelpers
from .io import ContextualizerConsumes, ContextualizerProduces
from .node import BaseContextualizerNode

# ------------------- Public API ------------------- #
__all__ = [
    "BaseContextualizerConfig",
    "DEFAULT_SITUATE_PROMPT",
    "DocumentScope",
    "OnChunkError",
    "ContextualizeViewHelpers",
    "ContextualizerConsumes",
    "ContextualizerProduces",
    "BaseContextualizerNode",
]
