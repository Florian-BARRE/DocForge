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
                (the SDK owns the exponential backoff schedule). None means "the caller does not pin
                it" and DISABLES the SDK's own retries (max_retries=0): the openai SDK ships a silent
                default of 2 retries, so a consumer that runs its OWN retry loop (VLM/embed) and does
                not pin here would otherwise stack two layers (e.g. 3×3 calls on an outage). Pinning a
                value lets a consumer with no own loop (llm/structgen/classify) delegate retries here.

        Returns:
            ChatOpenAI: The ready-to-invoke client.
        """
        # None means unpinned → 0: kill the SDK's built-in retries so the node's own loop is the ONLY
        # retry layer. A caller that pins a value delegates retries to the SDK on purpose.
        retries = {"max_retries": 0 if max_retries is None else max_retries}
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
                None means "the caller does not pin it" and DISABLES the SDK's own retries
                (max_retries=0): the embed node owns a retry + batch-split loop, so leaving the SDK at
                its silent default of 2 would stack two retry layers. Pinning a value delegates
                retries to the SDK for a consumer with no own loop.

        Returns:
            OpenAIEmbeddings: The ready-to-call client (ctx-length check off — local endpoints
            handle their own limits).
        """
        # None means unpinned → 0: the node's own loop is the sole retry layer (see ``chat``).
        retries = {"max_retries": 0 if max_retries is None else max_retries}
        return OpenAIEmbeddings(
            base_url=config.base_url,
            api_key=config.api_key or _EMPTY_KEY_PLACEHOLDER,
            model=config.model,
            timeout=config.timeout_seconds,
            check_embedding_ctx_length=False,
            **retries,
        )


__all__ = ["OpenAICompatHelpers"]
