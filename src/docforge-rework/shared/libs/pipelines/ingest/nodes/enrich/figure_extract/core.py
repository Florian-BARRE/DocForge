# ====== Code Summary ======
# The figure_extract node — opens the enrich stage: it turns the IR's figure blocks (crops already
# embedded by the parse stage) into the list of FigureItems the enrich ForEach iterates. Each item
# carries the crop bytes and its page coverage (the classifier's full-page-scan heuristic input).

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import DocumentIR, FigureItem


class FigureExtractConfig(NodeConfig):
    """figure_extract has no knob — it is a pure IR → items projection."""


class FigureExtractConsumes(NodeInput):
    """Input: the COMPLETE IR out of the parse stage (crops embedded)."""

    ir: DocumentIR = Field(description="The CROP-COMPLETE IR out of the parse stage.")


class FigureExtractProduces(NodeOutput):
    """Output: one FigureItem per croppable figure block — the enrich ForEach's list."""

    figures: list[FigureItem] = Field(
        default_factory=list,
        description="One item per croppable figure — the list the enrich foreach iterates.",
    )


@NodeRegistry.register("enrich")
class FigureExtractNode(ActionNode):
    """Project the IR's figure blocks into the per-item list the enrich ForEach runs over."""

    KIND = "figure_extract"
    NAME = "Figure extract"
    SUMMARY = "Turn the IR's figure blocks into the list of items the enrich loop iterates."
    HOW_IT_WORKS = (
        "Collects every figure block whose crop was embedded by the parse stage and emits one "
        "FigureItem per block (crop bytes + page coverage). Figures without a crop are skipped — "
        "there is nothing to classify or read."
    )
    Config = FigureExtractConfig
    UNIQUE_IN_GRAPH = True
    Consumes = FigureExtractConsumes
    Produces = FigureExtractProduces

    async def run(self, data: FigureExtractConsumes) -> FigureExtractProduces:
        """
        Build the enrich work list from the IR.

        Args:
            data (FigureExtractConsumes): The parsed, crop-complete IR.

        Returns:
            FigureExtractProduces: One item per figure block that has a crop.
        """
        # 1. One item per croppable figure block; coverage comes from the normalized bbox.
        figures: list[FigureItem] = []
        for block in data.ir.figure_blocks:
            if block.figure is None or block.figure.crop is None:
                self.logger.debug(f"Figure block '{block.id}' has no crop — skipped")
                continue
            x0, y0, x1, y1 = block.provenance.bbox
            coverage = max(0.0, min(1.0, abs(x1 - x0) * abs(y1 - y0)))
            figures.append(
                FigureItem(block_id=block.id, image=block.figure.crop, page_coverage=coverage)
            )

        # 2. Report the work list size — the enrich loop's fan-out.
        self.logger.info(f"Extracted {len(figures)} figure(s) to enrich")
        return FigureExtractProduces(figures=figures)


__all__ = ["FigureExtractNode", "FigureExtractConfig", "FigureExtractConsumes", "FigureExtractProduces"]
