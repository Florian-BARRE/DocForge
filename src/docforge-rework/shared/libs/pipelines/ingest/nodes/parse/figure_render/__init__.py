# ---------------------- Node ---------------------- #
# Importing core runs the @NodeRegistry.register decorator, so the node self-registers.
from .core import FigureRenderConfig, FigureRenderNode

# ------------------- Public API ------------------- #
__all__ = ["FigureRenderNode", "FigureRenderConfig"]

# ---------------------- Family declaration ---------------------- #
from shared_libs.pipelines.registry import FamilyMode, NodeRegistry

NodeRegistry.register_family(
    "render",
    title="Rendering",
    description=(
        "Completes the parsed IR: rasterises the pages and embeds each figure's crop, so the enrichment stage receives ready-to-work figures."
    ),
    mode=FamilyMode.STAGE,
)
