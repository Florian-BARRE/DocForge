# ---------------------- Node ---------------------- #
# Importing core runs the @NodeRegistry.register decorator, so the node self-registers.
from .core import OcrRapidOcrNode
from .engine import RapidOcrEngine

# ------------------- Public API ------------------- #
__all__ = ["OcrRapidOcrNode", "RapidOcrEngine"]
