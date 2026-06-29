# ====== Code Summary ======
# Stateless helpers for the parse stage steps (ported from the former parse ``ParseHelpers``).
# Contains pure IR transformations with no I/O and no logger dependency: stamping the parse
# ChainTrace onto the IR, building a minimal empty IR for the degraded no-parse outcome, and
# patching each figure block with its content-addressed crop key.

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import BlockType, ChainAttemptIR, ChainTrace, DocumentIR
from common_libs.pipelines.capabilities.chain import (
    ChainHelpers,
    ChainOutcome,
    chain_outcome_to_attempt_dicts,
)


class ParseHelpers:
    """
    Pure stateless helpers for the parse stage steps.

    All methods are static — no instance state, no logger. Every transformation returns a new
    ``DocumentIR`` (Pydantic ``model_copy``) so the IR threaded between steps is never mutated in
    place.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("ParseHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def stamp_parse_trace(ir: DocumentIR, outcome: ChainOutcome) -> DocumentIR:
        """
        Return a new DocumentIR with the parse ChainTrace appended.

        Preserves all existing ``chain_traces`` entries and appends a new one recording every
        provider attempt and which provider ultimately produced the accepted IR.

        Args:
            ir (DocumentIR): The IR returned by the winning parser provider (or the empty IR).
            outcome (ChainOutcome): The full chain execution result (attempts + winner).

        Returns:
            DocumentIR: A copy of ``ir`` with the parse trace appended.
        """
        return ir.model_copy(
            update={
                "chain_traces": [
                    *ir.chain_traces,
                    ChainTrace(
                        stage="parse",
                        attempts=[
                            ChainAttemptIR(**d) for d in chain_outcome_to_attempt_dicts(outcome)
                        ],
                        final_provider=outcome.final_provider,
                        degraded=outcome.degraded,
                        gate_tripped=(
                            ChainHelpers.gate_tripped(outcome) if outcome.degraded else None
                        ),
                    ),
                ],
            }
        )

    @staticmethod
    def empty_ir(doc_id: str, source_hash: str, page_count: int | None) -> DocumentIR:
        """
        Build a minimal, block-less DocumentIR for a degraded (no-parse) parse outcome.

        Used when there is no PDF view to parse, or when the parse gate's ``failure_policy=continue``
        and the chain exhausted: the document proceeds without a parse, ending "done" with zero blocks
        (and therefore zero chunks / not indexed). Carries the ingest-known identity fields so
        downstream persistence stays consistent.

        Args:
            doc_id (str): The effective document id (from ingest).
            source_hash (str): The original content address (from ingest).
            page_count (int | None): Page count of the PDF view, or None when there is no PDF.

        Returns:
            DocumentIR: An empty IR (no blocks, quality_score=0.0).
        """
        return DocumentIR(
            doc_id=doc_id,
            source_hash=source_hash,
            n_pages=page_count or 0,
            language="und",  # ISO 639-2 "undetermined" — no parser determined a language
            blocks=[],
            quality_score=0.0,
        )

    @staticmethod
    def patch_figure_crop_keys(ir: DocumentIR, figure_crop_keys: dict[str, str]) -> DocumentIR:
        """
        Return a new DocumentIR with each figure block's ``crop_key`` set.

        Iterates all blocks; for FIGURE blocks that have a figure payload, sets ``figure.crop_key``
        to the corresponding object-store key from ``figure_crop_keys``. Blocks with no entry in the
        map receive an empty string key.

        Args:
            ir (DocumentIR): The IR whose figure blocks need crop key annotation.
            figure_crop_keys (dict[str, str]): block_id -> object-store key.

        Returns:
            DocumentIR: A copy of ``ir`` with all figure ``crop_key`` fields populated.
        """
        updated_blocks = []
        for block in ir.blocks:
            if block.type == BlockType.FIGURE and block.figure is not None:
                crop_key = figure_crop_keys.get(block.id, "")
                updated_figure = block.figure.model_copy(update={"crop_key": crop_key})
                updated_blocks.append(block.model_copy(update={"figure": updated_figure}))
            else:
                updated_blocks.append(block)
        return ir.model_copy(update={"blocks": updated_blocks})


__all__ = ["ParseHelpers"]
