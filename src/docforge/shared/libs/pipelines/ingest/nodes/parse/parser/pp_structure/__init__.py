# ---------------------- Node ---------------------- #
# Importing core runs the @NodeRegistry.register decorator, so the node self-registers.
from .core import ParserPpStructureNode

# ------------------- Public API ------------------- #
__all__ = ["ParserPpStructureNode"]
