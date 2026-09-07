# ---------------------- Node ---------------------- #
# Importing core runs the @NodeRegistry.register decorator, so the node self-registers.
from .config import DocLanguageConfig
from .core import (
    DocLanguageConsumes,
    DocLanguageNode,
    DocLanguageProduces,
)
from .detector import LanguageDetector

# ------------------- Public API ------------------- #
__all__ = [
    "DocLanguageNode",
    "DocLanguageConfig",
    "DocLanguageConsumes",
    "DocLanguageProduces",
    "LanguageDetector",
]
