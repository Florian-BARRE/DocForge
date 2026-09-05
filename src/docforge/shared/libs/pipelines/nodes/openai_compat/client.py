# ====== Code Summary ======
# OpenAICompatHelpers — the ONE place an OpenAI-compatible client is constructed (chat and
# embeddings). Every consumer calls these instead of building ChatOpenAI/OpenAIEmbeddings
# by hand: the construction quirks (the empty-key placeholder some endpoints require, the
# timeout plumbing) live here exactly once. It also owns UsageAccumulator, the seam that lets a
# consumer running its OWN retry loop attribute the token usage of EVERY paid attempt (not just the
# final success): a single accumulator passed to every ``chat`` call across the loop sums each
# attempt's usage, so a call the node discards (a failed-but-billed attempt) still contributes.

# ====== Third-Party Library Imports ======
from langchain_core.callbacks.base import AsyncCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeUsage

# ====== Local Project Imports ======
from .config import OpenAICompatConfig

# Local endpoints (vLLM, bge_server…) require a NON-EMPTY key even when they ignore it.
_EMPTY_KEY_PLACEHOLDER = "unused"


class UsageAccumulator(AsyncCallbackHandler):
    """A LangChain callback that SUMS token usage across every chat attempt it observes.

    A node reading ``answer.usage_metadata`` only ever sees the FINAL successful call's usage, so a
    paid attempt that carried usage but was then discarded (an own-loop retry, or a response the node
    judged unusable) is never billed. Passing ONE of these to every ``OpenAICompatHelpers.chat`` call
    across a retry loop fixes that: the SDK fires ``on_llm_end`` for each attempt that returned a
    response, and this handler folds each one into a running ``NodeUsage`` the node then stamps on its
    output instead of the single-call metadata.

    Scope note: the accumulated usage is metered only where the execution record IS summed — the
    worker's ingest meter. Search-time query-LLM (rewrite / HyDE) runs INLINE in the request and its
    ``NodeUsage`` is discarded (the search runner keeps only the SearchResult), so there is no
    per-request cost sink for it today — a structural gap, not something this seam can close.
    """

    def __init__(self, model: str) -> None:
        """Start an empty accumulator keyed to the model whose calls it will sum."""
        super().__init__()
        self._model = model
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._seen = False

    @staticmethod
    def _extract(response: LLMResult) -> tuple[int, int] | None:
        """Pull (prompt, completion) tokens from an LLM result, defensively (None when unreadable).

        Reads the chat generation's ``usage_metadata`` (``input_tokens`` / ``output_tokens``) first,
        falling back to the aggregate ``llm_output['token_usage']`` some providers report instead. Any
        missing / odd payload yields None so a usage-capture miss can never raise on the paid loop.
        """
        # 1. The per-generation usage_metadata (the shape NodeUsage.from_usage_metadata parses).
        for generation_list in getattr(response, "generations", None) or []:
            for generation in generation_list:
                message = getattr(generation, "message", None)
                meta = getattr(message, "usage_metadata", None)
                if isinstance(meta, dict) and "input_tokens" in meta and "output_tokens" in meta:
                    try:
                        return int(meta["input_tokens"]), int(meta["output_tokens"])
                    except (TypeError, ValueError):
                        return None
        # 2. Fallback: the aggregate token_usage block on llm_output.
        token_usage = (getattr(response, "llm_output", None) or {}).get("token_usage")
        if isinstance(token_usage, dict):
            try:
                return int(token_usage["prompt_tokens"]), int(token_usage["completion_tokens"])
            except (KeyError, TypeError, ValueError):
                return None
        return None

    def record(self, prompt_tokens: int, completion_tokens: int) -> None:
        """Fold one attempt's token usage into the running total (the accumulation primitive)."""
        self._prompt_tokens += prompt_tokens
        self._completion_tokens += completion_tokens
        self._seen = True

    async def on_llm_end(self, response: LLMResult, **kwargs: object) -> None:
        """Accumulate the usage of one completed attempt (fires per attempt, incl. discarded ones)."""
        _ = kwargs
        tokens = self._extract(response)
        if tokens is not None:
            self.record(*tokens)

    @property
    def usage(self) -> NodeUsage | None:
        """The summed usage across every observed attempt, or None when none carried usage."""
        if not self._seen:
            return None
        return NodeUsage(
            model=self._model,
            prompt_tokens=self._prompt_tokens,
            completion_tokens=self._completion_tokens,
        )


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
        usage_sink: UsageAccumulator | None = None,
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
            usage_sink (UsageAccumulator | None): An optional accumulator attached as a callback so the
                token usage of EVERY attempt this client answers is summed. A consumer with its own
                retry loop passes ONE sink to each attempt's ``chat`` call to attribute every paid
                attempt (not just the final success). None = no usage accumulation on this client.

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
            callbacks=[usage_sink] if usage_sink is not None else None,
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


__all__ = ["OpenAICompatHelpers", "UsageAccumulator"]
