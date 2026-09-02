# ---------------------- Node ---------------------- #
# Importing core runs the @NodeRegistry.register decorator, so the node self-registers.
from .core import OcrPaddleNode

# ------------------- Public API ------------------- #
__all__ = ["OcrPaddleNode"]
