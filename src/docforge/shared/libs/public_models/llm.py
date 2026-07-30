# ====== Code Summary ======
# Shared LLM I/O artefacts. The prompt is a composition of LangChain messages (system / human /
# ai …) rather than a flat string, so nodes can build multi-message conversations. The completion
# holds the model's answer text. Referenced by LLM node CONSUMES/PRODUCES faces.

# ====== Third-Party Library Imports ======
from langchain_core.messages import AnyMessage

# ====== Local Project Imports ======
from .base import Artifact


class Prompt(Artifact):
    """
    A composition of chat messages to send to a language model.

    Attributes:
        messages (list[AnyMessage]): Ordered LangChain messages (e.g. a SystemMessage followed by
            a HumanMessage). Any LangChain message type is accepted.
    """

    messages: list[AnyMessage]


class Completion(Artifact):
    """
    A language model's generated answer.

    Attributes:
        text (str): The generated text.
    """

    text: str


__all__ = ["Prompt", "Completion"]
