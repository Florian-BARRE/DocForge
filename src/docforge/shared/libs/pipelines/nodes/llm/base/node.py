# ====== Code Summary ======
# Shared base for LLM chat provider nodes. Every OpenAI-style provider consumes a prompt and
# produces a completion the same way — only the LangChain chat client differs. So this base owns
# the fixed I/O faces and the run() that invokes the model, and leaves a single abstract hook,
# _chat_model(), for each provider to build its adapted LangChain client (ChatOpenAI, ChatMistralAI…).
#
# Being abstract (via _chat_model), this class is not registered and skips the ActionNode strict
# interface check; concrete providers implement _chat_model and declare their KIND + Config.

# ====== Standard Library Imports ======
from abc import abstractmethod

# ====== Third-Party Library Imports ======
from langchain_core.language_models import BaseChatModel

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeUsage
from shared_libs.pipelines.nodes.openai_compat import EndpointReachability
from shared_libs.public_models.llm import Completion

# ====== Local Project Imports ======
from .config import BaseLlmChatConfig
from .io import LlmChatConsumes, LlmChatProduces


class BaseLlmChatNode(ActionNode):
    """
    Abstract base for LLM chat nodes: shared I/O faces + a run() that invokes a LangChain model.

    Concrete providers implement _chat_model() to build their adapted LangChain chat client and
    declare their KIND / NAME / SUMMARY / Config.
    """

    Consumes = LlmChatConsumes
    Produces = LlmChatProduces

    async def preflight(self) -> None:
        """Verify the chat endpoint is reachable and its credentials accepted, before any spend."""
        config: BaseLlmChatConfig = self.config
        await EndpointReachability.check(
            node_kind=self.KIND,
            base_url=config.base_url,
            api_key=config.api_key,
            timeout_seconds=config.timeout_seconds,
        )

    @abstractmethod
    def _chat_model(self) -> BaseChatModel:
        """
        Build the provider-specific LangChain chat client from ``self.config`` + capabilities.

        Returns:
            BaseChatModel: The ready-to-invoke LangChain chat model.
        """
        ...

    async def run(self, data: LlmChatConsumes) -> LlmChatProduces:
        """
        Invoke the provider's LangChain model on the prompt messages and wrap the answer.

        Args:
            data (LlmChatConsumes): The resolved input carrying the prompt messages.

        Returns:
            LlmChatProduces: The model's completion.
        """
        # 1. Build the adapted LangChain client and invoke it on the message composition.
        model = self._chat_model()
        answer = await model.ainvoke(data.prompt.messages)

        # 2. Wrap the answer text in the output artefact (content is the plain text for chat models).
        output = LlmChatProduces(completion=Completion(text=answer.content))

        # 3. Stamp the paid-call token usage onto the output (None-safe; the engine lifts it).
        config: BaseLlmChatConfig = self.config
        output._usage = NodeUsage.from_usage_metadata(
            getattr(answer, "usage_metadata", None), config.model
        )
        return output


__all__ = ["BaseLlmChatNode"]
