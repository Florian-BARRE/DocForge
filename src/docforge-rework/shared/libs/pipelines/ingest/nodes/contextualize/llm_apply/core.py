# ====== Code Summary ======
# The llm contextualize APPLY node — the back half of the externalised llm contextualizer. It takes
# the Completions the llm ForEach produced (one per chunk, in the same order the prep emitted the
# prompts) and appends each one to the matching chunk's retrieval context, joined by POSITION —
# contextualize is strictly 1 chunk → 1 prompt → 1 completion, so a positional zip is the whole join
# (no chunk_id keying needed). An empty completion (the keep_raw fail-soft terminal, or a blank
# answer) leaves the chunk raw through the family's _with_context no-op, so one failed chunk never
# fails the document. It makes NO model call: appending is a pure structural join.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import Chunk
from shared_libs.public_models.llm import Completion

# ====== Local Project Imports ======
from ..base import BaseContextualizerNode


class ContextualizerLlmApplyConfig(NodeConfig):
    """No knobs — appending completions onto chunks is a pure positional join."""


class ContextualizerLlmApplyConsumes(NodeInput):
    """Input: the chunks + the completions the llm loop produced (one per chunk, in order)."""

    chunks: list[Chunk] = Field(
        default_factory=list, description="The chunks to append the situating snippets onto."
    )
    completions: list[Completion] = Field(
        default_factory=list,
        description="The situating completions the llm ForEach produced, in chunk order.",
    )


class ContextualizerLlmApplyProduces(NodeOutput):
    """Output: the same chunks, context grown (copies; raw text untouched)."""

    chunks: list[Chunk] = Field(
        default_factory=list, description="The SAME chunks, context grown (copies; raw untouched)."
    )


@NodeRegistry.register("contextualize")
class ContextualizerLlmApplyNode(ActionNode):
    """Append each situating completion to its chunk's context, joined by position."""

    KIND = "llm_apply"
    SELECTABLE = False  # internal wiring — the stage builder emits it, not a user-picked method
    NAME = "LLM context apply"
    SUMMARY = "Append the generated situating snippets back onto their chunks (by position)."
    HOW_IT_WORKS = (
        "Zips the chunks with the completions the llm loop produced (strict — one completion per "
        "chunk, same order the prep emitted the prompts) and appends each snippet to the matching "
        "chunk's context. An empty completion leaves the chunk raw — a failed chunk never fails the "
        "document."
    )
    Config = ContextualizerLlmApplyConfig
    Consumes = ContextualizerLlmApplyConsumes
    Produces = ContextualizerLlmApplyProduces

    async def run(self, data: ContextualizerLlmApplyConsumes) -> ContextualizerLlmApplyProduces:
        """
        Append each situating completion onto its chunk, joined by position.

        Args:
            data (ContextualizerLlmApplyConsumes): The chunks + the completions (one per chunk).

        Returns:
            ContextualizerLlmApplyProduces: The chunks with their context grown (copies).

        Raises:
            ValueError: If the completion count does not match the chunk count (a wiring bug —
                contextualize is strictly one completion per chunk).
        """
        # 1. Positional join — a length mismatch is a wiring bug that must surface (strict zip).
        chunks = [
            BaseContextualizerNode._with_context(chunk, completion.text)
            for chunk, completion in zip(data.chunks, data.completions, strict=True)
        ]
        enriched = sum(
            1 for before, after in zip(data.chunks, chunks, strict=True) if after is not before
        )
        self.logger.debug(f"Applied llm context onto {enriched}/{len(chunks)} chunk(s)")
        return ContextualizerLlmApplyProduces(chunks=chunks)


__all__ = [
    "ContextualizerLlmApplyNode",
    "ContextualizerLlmApplyConfig",
    "ContextualizerLlmApplyConsumes",
    "ContextualizerLlmApplyProduces",
]
