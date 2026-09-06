# ---------------------- Raw IR ---------------------- #
from .block import Block
from .block_table import BlockTable
from .block_figure import BlockFigure

# ---------------------- Enriched IR ---------------------- #
from .block_enrichment import BlockEnrichment, EnrichmentKind, EnrichmentStatus

# ------------------- Public API ------------------- #
__all__ = [
    "Block",
    "BlockTable",
    "BlockFigure",
    "BlockEnrichment",
    "EnrichmentKind",
    "EnrichmentStatus",
]
