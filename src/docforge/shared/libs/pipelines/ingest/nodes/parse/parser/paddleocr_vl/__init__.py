# ---------------------- Node ---------------------- #
# Importing core runs the @NodeRegistry.register decorator, so the node self-registers.
from .core import ParserPaddleOcrVlNode

# ------------------- Public API ------------------- #
__all__ = ["ParserPaddleOcrVlNode"]
