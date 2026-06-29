# ====== Code Summary ======
# EnrichIRWriter - rebuilds the DocumentIR from the per-figure FigureWork list. Only figure blocks
# present in the work list are rewritten (with their current enrichment + accumulated traces); every
# other block (non-figure, crop-less, or a figure whose crop failed to download) passes through
# untouched, exactly as the legacy per-figure path left them. The enrich stage applies the final work
# list onto the classified IR at aggregation time; intermediate steps thread the work list (not the
# IR), so this rebuild runs once per observable IR rather than once per step.

# ====== Standard Library Imports ======
from collections.abc import Iterable

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import DocumentIR

# ====== Local Project Imports ======
from .figure_work import FigureWork


class EnrichIRWriter:
    """
    Static helper that materialises the per-figure work onto the IR.

    ``apply`` rebuilds the IR's figure blocks from the work list; all other blocks are copied through
    unchanged. The IR is never mutated in place - a fresh copy is returned.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        """Block instantiation - this is a static-only helper class."""
        raise TypeError("EnrichIRWriter is a static-only class and cannot be instantiated.")

    @staticmethod
    def apply(ir: DocumentIR, works: Iterable[FigureWork]) -> DocumentIR:
        """
        Rebuild the IR with each work item's current enrichment + accumulated traces.

        Args:
            ir (DocumentIR): The IR to rewrite (its blocks are copied, never mutated in place).
            works (Iterable[FigureWork]): The per-figure work items (keyed onto blocks by id).

        Returns:
            DocumentIR: A copy of ``ir`` with the enrichable figure blocks updated; all other blocks
                are passed through unchanged.
        """
        # 1. Index the work items by the block id they enrich.
        by_block: dict[str, FigureWork] = {work.block_id: work for work in works}

        # 2. Rewrite only the figure blocks the classify step recorded; pass everything else through.
        new_blocks = []
        for block in ir.blocks:
            work = by_block.get(block.id)
            if work is None:
                new_blocks.append(block)
                continue
            new_blocks.append(
                block.model_copy(update={"figure": work.enrichment(), "chain_traces": work.traces()})
            )

        # 3. Assemble the enriched IR copy (same shape as the legacy ``ir.model_copy(update=blocks)``).
        return ir.model_copy(update={"blocks": new_blocks})


__all__ = ["EnrichIRWriter"]
