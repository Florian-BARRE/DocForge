# ====== Code Summary ======
# OpenAICompatHelpers — the ONE place an OpenAI-compatible client is constructed (chat and
# embeddings). Every consumer calls these instead of building ChatOpenAI/OpenAIEmbeddings
# by hand: the construction quirks (the empty-key placeholder some endpoints require, the
# timeout plumbing) live here exactly once.

# ====== Third-Party Library Imports ======
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from loggerplusplus import loggerplusplus

# ====== Local Project Imports ======
from .config import OpenAICompatConfig

# Local endpoints (vLLM, bge_server…) require a NON-EMPTY key even when they ignore it.
_EMPTY_KEY_PLACEHOLDER = "unused"


class OpenAICompatHelpers:
    """Static construction of OpenAI-compatible clients from an endpoint config."""

    logger = loggerplusplus.bind(identifier="OpenAICompatHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("OpenAICompatHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def chat(
        config: OpenAICompatConfig,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> ChatOpenAI:
        """
        Build a chat client on the configured endpoint.

        Args:
            config (OpenAICompatConfig): The endpoint (base_url / api_key / model / timeout).
            temperature (float): Sampling temperature for this consumer.
            max_tokens (int | None): Generation cap for this consumer (None = endpoint default).

        Returns:
            ChatOpenAI: The ready-to-invoke client.
        """
        return ChatOpenAI(
            base_url=config.base_url,
            api_key=config.api_key or _EMPTY_KEY_PLACEHOLDER,
            model=config.model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=config.timeout_seconds,
        )

    @staticmethod
    def embeddings(config: OpenAICompatConfig) -> OpenAIEmbeddings:
        """
        Build an embeddings client on the configured endpoint.

        Args:
            config (OpenAICompatConfig): The endpoint (base_url / api_key / model / timeout).

        Returns:
            OpenAIEmbeddings: The ready-to-call client (ctx-length check off — local endpoints
            handle their own limits).
        """
        return OpenAIEmbeddings(
            base_url=config.base_url,
            api_key=config.api_key or _EMPTY_KEY_PLACEHOLDER,
            model=config.model,
            timeout=config.timeout_seconds,
            check_embedding_ctx_length=False,
        )


__all__ = ["OpenAICompatHelpers"]
