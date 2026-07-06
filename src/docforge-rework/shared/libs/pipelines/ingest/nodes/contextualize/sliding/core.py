# ====== Code Summary ======
# The sliding contextualizer — gives each chunk a glimpse of its neighbours: the TAIL of
# the previous chunk and/or the HEAD of the next one (word-bounded). Zero cost, local; restores
# narrative continuity across chunk boundaries without duplicating whole chunks.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import Chunk

# ====== Local Project Imports ======
from ..base import BaseContextualizerConfig, BaseContextualizerNode, ContextualizerConsumes


class ContextualizerSlidingConfig(BaseContextualizerConfig):
    """Neighbour-window knobs (word counts — cheap and tokenizer-free)."""

    prev_words: int = Field(
        default=40, ge=0, description="Words taken from the END of the previous chunk (0 = off)."
    )
    next_words: int = Field(
        default=0, ge=0, description="Words taken from the START of the next chunk (0 = off)."
    )
    prev_template: str = Field(default="… {text}", description="Rendered form of the tail.")
    next_template: str = Field(default="{text} …", description="Rendered form of the head.")


@NodeRegistry.register("contextualize")
class ContextualizerSlidingNode(BaseContextualizerNode):
    """Prefix each chunk with a word-bounded glimpse of its neighbours."""

    KIND = "sliding"
    NAME = "Sliding context"
    SUMMARY = "Give each chunk the tail of the previous chunk / head of the next one."
    HOW_IT_WORKS = (
        "Takes the last prev_words of the previous chunk's RAW text (and/or the first "
        "next_words of the next one) and renders them as neighbour context. Zero cost."
    )
    Config = ContextualizerSlidingConfig
    UNIQUE_IN_GRAPH = True

    async def _context_for(
        self, index: int, chunks: list[Chunk], data: ContextualizerConsumes
    ) -> str | None:
        """Render the neighbour glimpses for chunks[index]."""
        config: ContextualizerSlidingConfig = self.config
        pieces: list[str] = []
        # 1. The tail of the previous chunk (raw text — context of neighbours would compound).
        if config.prev_words > 0 and index > 0:
            tail = " ".join(chunks[index - 1].text.split()[-config.prev_words:])
            if tail:
                pieces.append(config.prev_template.format(text=tail))
        # 2. The head of the next one.
        if config.next_words > 0 and index < len(chunks) - 1:
            head = " ".join(chunks[index + 1].text.split()[: config.next_words])
            if head:
                pieces.append(config.next_template.format(text=head))
        return "\n".join(pieces) if pieces else None


__all__ = ["ContextualizerSlidingNode", "ContextualizerSlidingConfig"]
