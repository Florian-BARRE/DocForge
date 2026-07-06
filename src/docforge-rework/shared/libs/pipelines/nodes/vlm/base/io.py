# ====== Code Summary ======
# The fixed I/O contract shared by EVERY VLM provider: ONE figure in (its ``context`` carrying any
# prior OCR reading, its ``kind`` stamped by the classifier), ONE EnrichmentEntry out. The entry is
# the single-slot terminal artefact of the enrich ForEach body — a VLM node closes its branch.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeInput, NodeOutput
from shared_libs.public_models import EnrichmentEntry, FigureItem


class VlmConsumes(NodeInput):
    """Input of any VLM provider — the figure to describe (context + kind already aboard)."""

    figure: FigureItem = Field(
        description="The figure to describe — its context carries any prior OCR reading."
    )


class VlmProduces(NodeOutput):
    """Output of any VLM provider — the branch's terminal entry (single slot, by contract)."""

    entry: EnrichmentEntry = Field(
        description="The branch terminal: description (+ parsed table), kind and OCR text aboard."
    )


__all__ = ["VlmConsumes", "VlmProduces"]
