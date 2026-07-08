# ====== Code Summary ======
# The llm contextualize PREP node — the LOUD, pre-spend front half of the externalised llm
# contextualizer. For each chunk it builds the document view the model will read (full / section /
# window, via the shared view helpers) and emits ONE situating Prompt per chunk, IN ORDER, never
# skipping — the items an llm ForEach fulfils into Completions the apply node zips back onto the
# chunks by position. It makes NO model call: that is the generic llm family's job downstream. The
# FULL view is chunk-independent, so it is built ONCE per run (no O(n²) regression); a view-building
# bug surfaces loudly (there is nothing to guard here — no spend happens in prep).

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import Chunk
from shared_libs.public_models.llm import Prompt

# ====== Local Project Imports ======
from ..base import ContextualizeViewHelpers, DocumentScope
from .config import ContextualizerLlmPrepConfig


class ContextualizerLlmPrepConsumes(NodeInput):
    """Input: the chunks to situate (raw or already contextualised upstream)."""

    chunks: list[Chunk] = Field(
        default_factory=list, description="The chunks to build one situating prompt per, in order."
    )


class ContextualizerLlmPrepProduces(NodeOutput):
    """Output: one situating Prompt per chunk — the items an llm ForEach fulfils, in chunk order."""

    prompts: list[Prompt] = Field(
        default_factory=list,
        description="One situating prompt per chunk, in the SAME order as the chunks (position is "
        "the join key the apply node zips completions back on).",
    )


@NodeRegistry.register("contextualize")
class ContextualizerLlmPrepNode(ActionNode):
    """Emit one situating prompt per chunk from its document view — the loud front half, no spend."""

    KIND = "llm_prep"
    SELECTABLE = False  # internal wiring — the stage builder emits it, not a user-picked method
    NAME = "LLM context prep"
    SUMMARY = "Build one situating prompt per chunk from its document view (no model call)."
    HOW_IT_WORKS = (
        "For each chunk, builds the document view the model reads (full text / the chunk's section / "
        "a neighbour window — the FULL view once per run) and emits one situating Prompt, in chunk "
        "order. No model call here: a generic llm ForEach fulfils the prompts downstream."
    )
    Config = ContextualizerLlmPrepConfig
    Consumes = ContextualizerLlmPrepConsumes
    Produces = ContextualizerLlmPrepProduces

    async def run(self, data: ContextualizerLlmPrepConsumes) -> ContextualizerLlmPrepProduces:
        """
        Emit one situating prompt per chunk, in order.

        Args:
            data (ContextualizerLlmPrepConsumes): The chunks to situate.

        Returns:
            ContextualizerLlmPrepProduces: One Prompt per chunk (chunk order preserved).
        """
        config: ContextualizerLlmPrepConfig = self.config
        chunks = data.chunks

        # 1. The full view is chunk-independent — built ONCE (a view-building bug surfaces here, loud).
        full_view = (
            ContextualizeViewHelpers.full_view(chunks, config.max_document_words)
            if config.document_scope == DocumentScope.FULL and chunks
            else None
        )

        # 2. One prompt per chunk, IN ORDER, never skipping — position is the apply node's join key.
        prompts: list[Prompt] = []
        for index in range(len(chunks)):
            view = ContextualizeViewHelpers.scoped_view(
                index, chunks, config.document_scope, config.window_chunks,
                config.max_document_words, full_view,
            )
            messages = ContextualizeViewHelpers.situate_messages(
                config.system_prompt, view, chunks[index].text
            )
            prompts.append(Prompt(messages=messages))

        self.logger.debug(f"Prepared {len(prompts)} situating prompt(s) over {len(chunks)} chunk(s)")
        return ContextualizerLlmPrepProduces(prompts=prompts)


__all__ = [
    "ContextualizerLlmPrepNode",
    "ContextualizerLlmPrepConfig",
    "ContextualizerLlmPrepConsumes",
    "ContextualizerLlmPrepProduces",
]
