# ====== Code Summary ======
# The figure_entry node — the model-free terminal of an enrich branch. It closes a figure's run
# with an EnrichmentEntry built from what the figure already carries (kind, OCR read_text), spending
# nothing. Two roles on the graph: the EXPLICIT decorative skip (the collection contract requires
# every branch to end on an entry — skipping is a visible node, not an absence), and the terminal
# of an OCR-only branch (scanned text without a VLM complement).

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import EnrichmentEntry, FigureItem


class FigureEntryConfig(NodeConfig):
    """figure_entry has no knob — it is a pure figure → entry projection."""


class FigureEntryConsumes(NodeInput):
    """Input: the figure to close (whatever its branch accumulated so far)."""

    figure: FigureItem = Field(
        description="The figure closing its branch (whatever it accumulated)."
    )


class FigureEntryProduces(NodeOutput):
    """Output: the branch's terminal entry (single slot, by the collection contract)."""

    entry: EnrichmentEntry = Field(
        description="The branch terminal: kind + OCR text carried over, no model call."
    )


@NodeRegistry.register("enrich")
class FigureEntryNode(ActionNode):
    """Close an enrich branch without a model call — skip or OCR-only terminal."""

    KIND = "figure_entry"
    NAME = "Figure entry"
    SUMMARY = "Close an enrich branch with what the figure already carries (no model call)."
    HOW_IT_WORKS = (
        "Builds the terminal EnrichmentEntry from the figure's stamped kind and accumulated OCR "
        "read_text. Wire it as the decorative branch (zero spend, but the skip stays visible on the "
        "graph) or after an OCR when no VLM complement is wanted."
    )
    Config = FigureEntryConfig
    Consumes = FigureEntryConsumes
    Produces = FigureEntryProduces

    async def run(self, data: FigureEntryConsumes) -> FigureEntryProduces:
        """
        Project the figure into its terminal entry.

        Args:
            data (FigureEntryConsumes): The figure closing its branch.

        Returns:
            FigureEntryProduces: The entry carrying the figure's kind and OCR text (if any).
        """
        # 1. Everything the branch learned is already on the figure — project it.
        return FigureEntryProduces(
            entry=EnrichmentEntry(
                block_id=data.figure.block_id,
                kind=data.figure.kind,
                ocr_text=data.figure.read_text or None,
            )
        )


__all__ = ["FigureEntryNode", "FigureEntryConfig", "FigureEntryConsumes", "FigureEntryProduces"]
