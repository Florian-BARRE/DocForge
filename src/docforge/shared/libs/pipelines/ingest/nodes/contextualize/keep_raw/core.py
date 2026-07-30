# ====== Code Summary ======
# The contextualize KEEP_RAW node — a model-free ForEach terminal. It is the graph-level embodiment
# of the old llm contextualizer's ``on_error=keep_raw`` policy: when an llm chain exhausts every
# provider on a chunk's situating prompt, the body routes OnFailure here instead of failing the item,
# and this node emits an EMPTY Completion. The apply node then leaves that chunk raw (its
# _with_context no-ops on a blank piece), so the document survives — only that chunk misses its
# situating snippet. It makes NO model call (its whole point is to spend nothing), so it uniformly
# closes the ForEach body on the same Completion artefact the llm steps produce.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models.llm import Completion, Prompt


class ContextualizerKeepRawConfig(NodeConfig):
    """No knobs — the fail-soft terminal emits an empty completion and spends nothing."""


class ContextualizerKeepRawConsumes(NodeInput):
    """Input: the situating prompt whose llm chain exhausted every provider (kept for symmetry)."""

    prompt: Prompt = Field(
        description="The failed chunk's situating prompt — its chain exhausted every provider."
    )


class ContextualizerKeepRawProduces(NodeOutput):
    """Output: an empty Completion (the uniform ForEach-body terminal artefact)."""

    completion: Completion = Field(
        description="Empty completion — the apply node leaves the chunk raw (no situating snippet)."
    )


@NodeRegistry.register("contextualize")
class ContextualizerKeepRawNode(ActionNode):
    """The fail-soft ForEach terminal — emit an empty completion so the chunk stays raw."""

    KIND = "keep_raw"
    SELECTABLE = False  # internal fail-soft ForEach terminal — the stage builder emits it
    NAME = "Keep chunk raw"
    SUMMARY = "Emit an empty completion for a chunk whose situating chain failed."
    HOW_IT_WORKS = (
        "A model-free terminal wired OnFailure from an llm chain's last step: it emits an empty "
        "Completion, so the apply node leaves that chunk raw and the document survives (the graph "
        "form of on_error=keep_raw)."
    )
    Config = ContextualizerKeepRawConfig
    Consumes = ContextualizerKeepRawConsumes
    Produces = ContextualizerKeepRawProduces

    async def run(self, data: ContextualizerKeepRawConsumes) -> ContextualizerKeepRawProduces:
        """
        Emit an empty completion so the chunk passes through un-contextualised.

        Args:
            data (ContextualizerKeepRawConsumes): The failed chunk's situating prompt.

        Returns:
            ContextualizerKeepRawProduces: An empty completion (the chunk stays raw).
        """
        self.logger.debug("Kept a chunk raw — its situating chain exhausted every provider")
        return ContextualizerKeepRawProduces(completion=Completion(text=""))


__all__ = [
    "ContextualizerKeepRawNode",
    "ContextualizerKeepRawConfig",
    "ContextualizerKeepRawConsumes",
    "ContextualizerKeepRawProduces",
]
