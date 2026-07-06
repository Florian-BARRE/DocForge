# ---------------------- Node ---------------------- #
# Importing core runs the @NodeRegistry.register decorator, so the node self-registers.
from .core import PdfProbeNode, PdfProbeConfig

# ------------------- Public API ------------------- #
__all__ = ["PdfProbeNode", "PdfProbeConfig"]
