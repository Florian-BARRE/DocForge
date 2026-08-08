# ====== Code Summary ======
# OpenAI-compatible LLM node — talks to any /chat/completions endpoint via LangChain's ChatOpenAI.
# It only declares its identity + Config and builds the adapted LangChain client; the shared I/O
# faces and the run() invocation live in the family base node.

# ====== Third-Party Library Imports ======
from langchain_core.language_models import BaseChatModel

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.openai_compat import OpenAICompatHelpers
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from ..base import BaseLlmChatNode
from .config import LlmOpenAICompatibleConfig


@NodeRegistry.register("llm")
class LlmOpenAICompatibleNode(BaseLlmChatNode):
    """
    Call any OpenAI-compatible chat-completions endpoint through LangChain's ChatOpenAI.

    Configured with an endpoint URL, a model, an api key and generation parameters (all in its
    Config). Produces the model's completion for the given prompt messages.
    """

    KIND = "openai_compatible"
    NAME = "OpenAI-compatible LLM"
    SUMMARY = "Call any OpenAI-compatible chat-completions endpoint."
    HOW_IT_WORKS = (
        "Builds a LangChain ChatOpenAI client pointed at <base_url> and invokes it on the prompt "
        "messages with the configured model and generation parameters."
    )
    Config = LlmOpenAICompatibleConfig

    def _chat_model(self) -> BaseChatModel:
        """Build the chat client through the shared factory."""
        config: LlmOpenAICompatibleConfig = self.config
        return OpenAICompatHelpers.chat(
            config,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            max_retries=config.max_retries,
        )


__all__ = ["LlmOpenAICompatibleNode"]
