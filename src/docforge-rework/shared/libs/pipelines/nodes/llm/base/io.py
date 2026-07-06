# ====== Code Summary ======
# Shared I/O faces for LLM chat nodes: they consume a Prompt and produce a Completion, both over
# the shared artefact vocabulary. Every LLM provider node reuses these faces.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeInput, NodeOutput
from shared_libs.public_models.llm import Completion, Prompt


class LlmChatConsumes(NodeInput):
    """
    Input face of an LLM chat node.

    Attributes:
        prompt (Prompt): The prompt, bound from an upstream node or the run input.
    """

    prompt: Prompt = Field(description="The chat messages to complete.")


class LlmChatProduces(NodeOutput):
    """
    Output face of an LLM chat node.

    Attributes:
        completion (Completion): The model's generated answer.
    """

    completion: Completion = Field(description="The model's completion.")


__all__ = ["LlmChatConsumes", "LlmChatProduces"]
