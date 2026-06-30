# ====== Code Summary ======
# The contextualize stage — a GROUP wrapping its single contextualize node. It consumes the chunk list
# (from the chunk stage) and the enriched IR (from the enrich stage) via FromNode bindings, hands them
# to the node through the group input, and surfaces the node's contextualized chunks as the stage
# output consumed by metagen / embed_index. A single-node group: its control axis is trivial (no
# transitions), its value is the inter-stage data wiring + the stage-level Output contract.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain import Chunk, DocumentIR
from common_libs.pipelines.flow import FromNode, GroupNode, NodeInput, NodeOutput

# ====== Local Project Imports ======
from .config import ContextualizeConfig
from .nodes import ContextualizeNode


class ContextualizeStageInput(NodeInput):
    """
    The contextualize stage input — the chunks + the enriched IR from the upstream stages.

    Attributes:
        chunks (list[Chunk]): The chunk list produced by the chunk stage (embed_text empty on entry).
        ir (DocumentIR): The enriched IR for the same document (read for its title only).
    """

    chunks: Annotated[list[Chunk], FromNode("chunk", "chunks")]
    ir: Annotated[DocumentIR, FromNode("enrich", "ir")]


class ContextualizeStageOutput(NodeOutput):
    """
    The contextualize stage output — the chunks with ``embed_text`` populated.

    Attributes:
        chunks (list[Chunk]): The contextualized chunks consumed by metagen / embed_index.
    """

    chunks: list[Chunk]


class ContextualizeStage(GroupNode):
    """Contextualize: build each chunk's embed_text from doc title + breadcrumb + body."""

    Input = ContextualizeStageInput
    Output = ContextualizeStageOutput

    def __init__(self, config: ContextualizeConfig | None = None) -> None:
        """
        Wire the single contextualize node as the stage body.

        Args:
            config (ContextualizeConfig | None): Header-template knobs threaded to the node. When
                None, the node falls back to its default config.
        """
        super().__init__("contextualize", [ContextualizeNode("contextualize", config)], [])

    def assemble(self, outputs: dict, terminal: NodeOutput) -> ContextualizeStageOutput:
        """
        Surface the single node's contextualized chunks as the stage output.

        Args:
            outputs (dict): The child outputs by id (here, only the contextualize node).
            terminal (NodeOutput): The terminal node's output (the contextualize node's output).

        Returns:
            ContextualizeStageOutput: The contextualized chunks.
        """
        # 1. The single node IS the terminal — re-shape its output into the stage contract.
        return ContextualizeStageOutput(chunks=terminal.chunks)


__all__ = ["ContextualizeStage", "ContextualizeStageInput", "ContextualizeStageOutput"]
