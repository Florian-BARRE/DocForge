# ---------------------- Node ---------------------- #
# Importing core runs the @NodeRegistry.register decorator, so the node self-registers.
from .core import OcrRapidOcrNode

# ------------------- Public API ------------------- #
__all__ = ["OcrRapidOcrNode"]
