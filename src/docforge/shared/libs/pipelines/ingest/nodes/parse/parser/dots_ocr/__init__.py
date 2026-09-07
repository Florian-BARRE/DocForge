# ---------------------- Node ---------------------- #
# Importing core runs the @NodeRegistry.register decorator, so the node self-registers.
from .core import ParserDotsOcrNode

# ------------------- Public API ------------------- #
__all__ = ["ParserDotsOcrNode"]
