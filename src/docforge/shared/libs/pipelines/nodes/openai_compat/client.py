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
        seed: int | None = None,
        max_retries: int | None = None,
    ) -> ChatOpenAI:
        """
        Build a chat client on the configured endpoint.

        Args:
            config (OpenAICompatConfig): The endpoint (base_url / api_key / model / timeout).
            temperature (float): Sampling temperature for this consumer.
            max_tokens (int | None): Generation cap for this consumer (None = endpoint default).
            seed (int | None): Sampling seed forwarded when set (None = the provider's default,
                i.e. unpinned) — lets a consumer opt into reproducible outputs.
            max_retries (int | None): Bounded transient-retry count handed to the openai SDK client
                (the SDK owns the exponential backoff schedule). None keeps the client's own default
                — used by consumers that own a retry loop (VLM) so the SDK layer is not doubled.

        Returns:
            ChatOpenAI: The ready-to-invoke client.
        """
        # Forward max_retries only when the caller pins it, so a consumer with its OWN retry loop
        # (VLM) keeps the client at its default and does not stack two retry layers.
        retries = {} if max_retries is None else {"max_retries": max_retries}
        return ChatOpenAI(
            base_url=config.base_url,
            api_key=config.api_key or _EMPTY_KEY_PLACEHOLDER,
            model=config.model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=config.timeout_seconds,
            seed=seed,
            **retries,
        )

    @staticmethod
    def embeddings(config: OpenAICompatConfig, max_retries: int | None = None) -> OpenAIEmbeddings:
        """
        Build an embeddings client on the configured endpoint.

        Args:
            config (OpenAICompatConfig): The endpoint (base_url / api_key / model / timeout).
            max_retries (int | None): Bounded transient-retry count handed to the openai SDK client.
                None keeps the client's own default — used by the embed node, which owns a retry +
                batch-split loop, so the SDK layer is not doubled.

        Returns:
            OpenAIEmbeddings: The ready-to-call client (ctx-length check off — local endpoints
            handle their own limits).
        """
        retries = {} if max_retries is None else {"max_retries": max_retries}
        return OpenAIEmbeddings(
            base_url=config.base_url,
            api_key=config.api_key or _EMPTY_KEY_PLACEHOLDER,
            model=config.model,
            timeout=config.timeout_seconds,
            check_embedding_ctx_length=False,
            **retries,
        )


__all__ = ["OpenAICompatHelpers"]
