# ====== Code Summary ======
# The enrich_apply node — closes the enrich stage: it folds the ForEach's collected entries back
# into the IR's figure slots (kind, ocr_text, description, data_table). After it, the IR is the
# ENRICHED canonical document the chunking stage consumes. The per-attempt trace (which provider
# ran, scores, errors) is NOT here — it lives in the engine's per-item execution records.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import DocumentIR, EnrichmentEntry, FigureKind


class EnrichApplyConfig(NodeConfig):
    """enrich_apply has no knob — it is a pure entries → IR fold."""


class EnrichApplyConsumes(NodeInput):
    """Input: the crop-complete IR + everything the enrich loop collected."""

    ir: DocumentIR = Field(description="The crop-complete IR the entries are folded into.")
    entries: list[EnrichmentEntry] = Field(
        default_factory=list,
        description="Everything the enrich loop collected (one entry per treated figure).",
    )


class EnrichApplyProduces(NodeOutput):
    """Output: the ENRICHED IR — figure slots filled, ready for chunking."""

    ir: DocumentIR = Field(description="The ENRICHED IR — figure slots filled, ready for chunking.")


@NodeRegistry.register("enrich")
class EnrichApplyNode(ActionNode):
    """Fold the collected enrichment entries back into the IR's figure slots."""

    KIND = "enrich_apply"
    NAME = "Enrich apply"
    SUMMARY = "Write the collected entries (kind, OCR text, description, table) into the IR."
    HOW_IT_WORKS = (
        "Matches each entry to its figure block by block_id and fills the block's figure slot: "
        "the classified kind, the OCR text, the VLM description and the chart rows. Blocks "
        "without an entry (no crop, or skipped) keep their parse-time slot untouched."
    )
    Config = EnrichApplyConfig
    UNIQUE_IN_GRAPH = True
    Consumes = EnrichApplyConsumes
    Produces = EnrichApplyProduces

    async def run(self, data: EnrichApplyConsumes) -> EnrichApplyProduces:
        """
        Apply every entry to its figure block.

        Args:
            data (EnrichApplyConsumes): The IR and the enrich loop's entries.

        Returns:
            EnrichApplyProduces: The same IR, its figure slots enriched in place (the IR is
            stage-owned data flowing forward — copying every crop again would double the memory).
            INVARIANT for callers: this is the very object handed in as ``run_input["ir"]`` —
            do not reuse the run input after the run expecting the pre-enrichment IR.
        """
        # 1. Index the entries by their target block.
        by_block = {entry.block_id: entry for entry in data.entries}

        # 2. Fill each matched figure slot; unmatched blocks keep their parse-time state.
        applied = 0
        for block in data.ir.figure_blocks:
            entry = by_block.get(block.id)
            if entry is None or block.figure is None:
                continue
            # The classifier's kind is one of the FigureKind values by construction; an unknown
            # value (a future class this build does not know) keeps the parse-time placeholder.
            if entry.kind in FigureKind:
                block.figure.kind = FigureKind(entry.kind)
            block.figure.ocr_text = entry.ocr_text
            block.figure.description = entry.description
            block.figure.data_table = entry.data_table
            applied += 1

        # 3. Report the fold — the enrich stage's outcome in one line.
        self.logger.info(f"Applied {applied}/{len(data.entries)} enrichment entr(ies) to the IR")
        return EnrichApplyProduces(ir=data.ir)


__all__ = ["EnrichApplyNode", "EnrichApplyConfig", "EnrichApplyConsumes", "EnrichApplyProduces"]
