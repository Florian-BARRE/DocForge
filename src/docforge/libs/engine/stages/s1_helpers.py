# ====== Code Summary ======
# Stateless helpers for the S1 parse stage.
# Contains pure IR transformations (chain-trace stamping, figure crop key patching)
# that carry no logger dependency and are fully separated from async/S3 concerns.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
# (none)

# ====== Internal Project Imports ======
from libs.core.ir.models import BlockType, ChainAttemptIR, ChainTrace, DocumentIR
from libs.capabilities.chain import ChainOutcome, chain_outcome_to_attempt_dicts


class S1Helpers:
    """
    Pure stateless helpers for the S1 parse stage.

    All methods are static — no instance state, no logger.
    Logger discipline: no logger binding because every method is @staticmethod
    (none uses cls.logger).  If a @classmethod is added later that logs,
    bind ``logger = loggerplusplus.bind(identifier="S1Helpers")`` at class level.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Prevent instantiation — this is a static-only helper class."""
        raise TypeError("S1Helpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def stamp_parse_trace(ir: DocumentIR, outcome: ChainOutcome) -> DocumentIR:
        """
        Return a new DocumentIR with the parse ChainTrace appended.

        Preserves all existing ``chain_traces`` entries and appends a new one
        recording every provider attempt and which provider ultimately produced
        the accepted IR.

        Args:
            ir (DocumentIR): The IR returned by the winning parser provider.
            outcome (ChainOutcome): The full chain execution result (attempts + winner).

        Returns:
            DocumentIR: A copy of ``ir`` with the parse trace appended.
        """
        return ir.model_copy(update={
            "chain_traces": [
                *ir.chain_traces,
                ChainTrace(
                    stage="parse",
                    attempts=[
                        ChainAttemptIR(**d)
                        for d in chain_outcome_to_attempt_dicts(outcome)
                    ],
                    final_provider=outcome.final_provider,
                ),
            ],
        })

    @staticmethod
    def patch_figure_crop_keys(
        ir: DocumentIR, figure_crop_keys: dict[str, str]
    ) -> DocumentIR:
        """
        Return a new DocumentIR with each figure block's ``crop_key`` set.

        Iterates all blocks; for FIGURE blocks that have a figure payload, sets
        ``figure.crop_key`` to the corresponding S3 key from ``figure_crop_keys``.
        Blocks with no entry in the map receive an empty string key.

        Args:
            ir (DocumentIR): The IR whose figure blocks need crop key annotation.
            figure_crop_keys (dict[str, str]): block_id → S3 object-store key.

        Returns:
            DocumentIR: A copy of ``ir`` with all figure ``crop_key`` fields populated.
        """
        updated_blocks = []
        for block in ir.blocks:
            if block.type == BlockType.FIGURE and block.figure is not None:
                crop_key = figure_crop_keys.get(block.id, "")
                updated_figure = block.figure.model_copy(update={"crop_key": crop_key})
                updated_block = block.model_copy(update={"figure": updated_figure})
                updated_blocks.append(updated_block)
            else:
                updated_blocks.append(block)
        return ir.model_copy(update={"blocks": updated_blocks})


__all__ = ["S1Helpers"]
