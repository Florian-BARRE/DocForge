# ====== Code Summary ======
# The fixed I/O contract shared by EVERY OCR provider: ONE figure in, the SAME figure out with its
# ``read_text`` filled by the reading, plus the provider's confidence as the output SCORE — which is
# what a ScoreBelow transition escalates on. Inside a ForEach body this gives per-figure OCR with
# per-figure escalation, all visible on the graph.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeInput, ScoredOutput
from shared_libs.public_models import FigureItem


class OcrConsumes(NodeInput):
    """Input of any OCR provider — the figure to read."""

    figure: FigureItem = Field(description="The figure whose crop is to be read.")


class OcrProduces(ScoredOutput):
    """Output of any OCR provider — the figure with ``read_text`` filled, scored by confidence."""

    figure: FigureItem = Field(
        description="The SAME figure with its read_text filled by the reading (a copy)."
    )


__all__ = ["OcrConsumes", "OcrProduces"]
