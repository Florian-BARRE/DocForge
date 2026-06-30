# ====== Code Summary ======
# The contextualize node — the single elementary action of the contextualize stage. It reads the chunk
# list + the enriched IR from its enclosing group's input, mutates each chunk's ``embed_text`` in place
# (doc title + heading breadcrumb + body, per the injected ContextualizeConfig) and returns the same
# chunk list. Pure logic — no provider, no service. One self-contained file: its typed Input (bound to
# the group input), its typed Output, its Config, and its logic.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain import Chunk, DocumentIR
from common_libs.pipelines.flow import ActionNode, Context, FromGroupInput, NodeInput, NodeOutput

# ====== Local Project Imports ======
from ..config import ContextualizeConfig
from .helpers import ContextualizeHelpers


class ContextualizeNodeInput(NodeInput):
    """
    Input of the contextualize node — read from the contextualize stage's input.

    Attributes:
        chunks (list[Chunk]): The chunk list produced by the chunk stage (embed_text empty on entry).
        ir (DocumentIR): The enriched IR for the same document (read for its title only).
    """

    chunks: Annotated[list[Chunk], FromGroupInput()]
    ir: Annotated[DocumentIR, FromGroupInput()]


class ContextualizeNodeOutput(NodeOutput):
    """
    Output of the contextualize node — the same chunks with ``embed_text`` populated.

    Attributes:
        chunks (list[Chunk]): The chunks with ``embed_text`` populated.
    """

    chunks: list[Chunk]


class ContextualizeNode(ActionNode):
    """
    Build each chunk's embed_text from title + breadcrumb + body (pure logic, no service).

    Reads ``chunks`` + ``ir`` from its parent stage input; writes each chunk's ``embed_text`` and
    returns the chunk list. The header template is driven by the injected ContextualizeConfig.
    """

    Input = ContextualizeNodeInput
    Output = ContextualizeNodeOutput
    Config = ContextualizeConfig

    def __init__(self, node_id: str, config: ContextualizeConfig | None = None) -> None:
        """
        Wire the node around its contextualization config.

        Args:
            node_id (str): The node's id, unique among its siblings.
            config (ContextualizeConfig | None): Header-template controls (toggles + separators).
                When None, the default config is used.
        """
        super().__init__(node_id)
        self._config = config if config is not None else ContextualizeConfig()

    async def execute(self, ctx: Context) -> ContextualizeNodeOutput:
        """
        Assemble each chunk's embed_text and return the contextualized chunks.

        Args:
            ctx (Context): Carries the resolved input (chunks + IR). No service is needed.

        Returns:
            ContextualizeNodeOutput: The same chunk list with ``embed_text`` populated.
        """
        # 1. Resolve the document title once (prepended per chunk when enabled).
        chunks = ctx.input.chunks
        ir = ctx.input.ir
        doc_title = (ir.title or "").strip()
        self.logger.info(f"Contextualize started: doc_id={ir.doc_id} chunks={len(chunks)}")

        # 2. Mutate each chunk's embed_text in place, counting the non-empty ones.
        n_contextualized = 0
        for chunk in chunks:
            chunk.embed_text = ContextualizeHelpers.build_embed_text(
                chunk=chunk, doc_title=doc_title, cfg=self._config
            )
            if chunk.embed_text:
                n_contextualized += 1

        # 3. Return the same chunk list (mutated in place).
        self.logger.info(
            f"Contextualize done: doc_id={ir.doc_id} "
            f"contextualized={n_contextualized}/{len(chunks)}"
        )
        return ContextualizeNodeOutput(chunks=chunks)


__all__ = ["ContextualizeNode", "ContextualizeNodeInput", "ContextualizeNodeOutput"]
