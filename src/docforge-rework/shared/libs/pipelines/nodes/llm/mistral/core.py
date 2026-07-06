# ====== Code Summary ======
# Mistral LLM node — talks to the Mistral chat API via LangChain's ChatMistralAI. It only declares
# its identity + Config and builds the adapted LangChain client; the shared I/O faces and the run()
# invocation live in the family base node.

# ====== Third-Party Library Imports ======
from langchain_core.language_models import BaseChatModel
from langchain_mistralai import ChatMistralAI

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from ..base import BaseLlmChatNode
from .config import LlmMistralConfig


@NodeRegistry.register("llm")
class LlmMistralNode(BaseLlmChatNode):
    """
    Call the Mistral chat API through LangChain's ChatMistralAI.

    Configured with a model choice, an api key and generation parameters (all in its Config).
    Produces the model's completion for the given prompt messages.
    """

    KIND = "mistral"
    NAME = "Mistral"
    SUMMARY = "Call the Mistral chat-completions API."
    HOW_IT_WORKS = (
        "Builds a LangChain ChatMistralAI client and invokes it on the prompt messages with the "
        "selected model and generation parameters."
    )
    Config = LlmMistralConfig

    def _chat_model(self) -> BaseChatModel:
        """Build a ChatMistralAI client from the config."""
        config: LlmMistralConfig = self.config
        return ChatMistralAI(
            endpoint=config.base_url,
            api_key=config.api_key,
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            timeout=config.timeout_seconds,
        )


__all__ = ["LlmMistralNode"]
