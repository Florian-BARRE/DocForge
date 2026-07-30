# ====== Code Summary ======
# The fixed I/O contract shared by EVERY VLM provider: ONE figure in (its ``context`` carrying any
# prior OCR reading, its ``kind`` stamped by the classifier), ONE EnrichmentEntry out, plus the
# provider's confidence as the output SCORE — which is what a ScoreBelow transition escalates on.
# The entry is NOT the ForEach terminal itself (that would be a 2-slot terminal, forbidden): a
# model-free ``vlm_entry`` node projects this scored output onto the single-slot ``{entry}`` terminal.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeInput, ScoredOutput
from shared_libs.public_models import EnrichmentEntry, FigureItem


class VlmConsumes(NodeInput):
    """Input of any VLM provider — the figure to describe (context + kind already aboard)."""

    figure: FigureItem = Field(
        description="The figure to describe — its context carries any prior OCR reading."
    )


class VlmProduces(ScoredOutput):
    """Output of any VLM provider — the branch's entry, scored by the provider's confidence."""

    entry: EnrichmentEntry = Field(
        description="The branch entry: description (+ parsed table), kind and OCR text aboard."
    )


__all__ = ["VlmConsumes", "VlmProduces"]
