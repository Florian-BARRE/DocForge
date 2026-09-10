# ====== Code Summary ======
# LangChainClientPool — a process-wide pool of LangChain ChatOpenAI / OpenAIEmbeddings clients shared
# by every hosted LLM/VLM/embed node. Each such client brings its OWN openai.AsyncOpenAI (an httpx
# connection pool + TLS). The callers run inside a per-item ForEach (metagen/contextualize/enrich), so
# a fresh client per call meant N figures/chunks = N clients, none closed → connection/FD accumulation
# on the hosted endpoint. The pool caches one client per resolved CONSTRUCTION identity (endpoint,
# credentials, model, generation params, retries) so successive ForEach items and retries reuse the
# one kept-alive client. Per-invocation concerns — the UsageAccumulator callback — are NOT baked into
# construction (that would fragment the key and tie usage to a shared client); the caller passes the
# sink per call via ``ainvoke(..., config={"callbacks": [sink]})``. A node stays pure: a pooled client
# is a provider-connection resource, never DB/S3 I/O. One event loop per process (worker / app search)
# makes a loop-bound cached client safe; a client whose underlying transport is found closed is
# recreated defensively. A close-all runs at process exit (atexit) and via the explicit shutdown() the
# worker/app lifespan calls, so no connection leaks on an orderly stop (mirrors HttpClientPool).

# ====== Standard Library Imports ======
import asyncio
import atexit

# ====== Third-Party Library Imports ======
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from loggerplusplus import loggerplusplus

# The chat cache key: every bit that shapes a distinct ChatOpenAI client. Two callers differing on any
# of these must never share a client (different credentials, model, sampling or retry behaviour).
_ChatKey = tuple[str, str, str, float, int | None, float, int | None, int]
# The embeddings cache key: the embeddings client carries no sampling/seed knobs.
_EmbedKey = tuple[str, str, str, float, int]


class LangChainClientPool:
    """Process-wide registry of reusable LangChain clients, keyed by construction identity."""

    logger = loggerplusplus.bind(identifier="LangChainClientPool")
    _chat_clients: dict[_ChatKey, ChatOpenAI] = {}
    _embed_clients: dict[_EmbedKey, OpenAIEmbeddings] = {}
    _atexit_registered: bool = False

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("LangChainClientPool is a static-only class and cannot be instantiated.")

    @staticmethod
    def __underlying(client: ChatOpenAI | OpenAIEmbeddings) -> object | None:
        """Return the wrapped ``openai.AsyncOpenAI`` (the transport owner) of either client type.

        ChatOpenAI exposes it as ``root_async_client``; OpenAIEmbeddings builds it lazily under
        ``async_client._client``. Returns None for anything else (e.g. a test stand-in) so the
        closed-check and shutdown both degrade gracefully.
        """
        root = getattr(client, "root_async_client", None)
        if root is not None:
            return root
        resource = getattr(client, "async_client", None)
        return getattr(resource, "_client", None)

    @classmethod
    def __is_closed(cls, client: ChatOpenAI | OpenAIEmbeddings) -> bool:
        """Whether the client's underlying transport is closed (→ must be recreated before reuse).

        A client cached on a now-closed event loop reports its transport closed; treat any client
        whose closed-state cannot be read (no underlying transport) as open so a stand-in is reused.
        """
        underlying = cls.__underlying(client)
        is_closed = getattr(underlying, "is_closed", None)
        try:
            return bool(is_closed()) if callable(is_closed) else False
        except Exception:  # noqa: BLE001 — a probe of closed-state must never raise on the hot path
            return False

    @classmethod
    def __ensure_atexit(cls) -> None:
        """Register the process-exit close-all exactly once (lazy, on first client creation)."""
        if not cls._atexit_registered:
            atexit.register(cls.__atexit_close)
            cls._atexit_registered = True

    @classmethod
    def __atexit_close(cls) -> None:
        """Best-effort synchronous close-all at interpreter exit (no running loop expected here)."""
        if not cls._chat_clients and not cls._embed_clients:
            return
        try:
            asyncio.run(cls.shutdown())
        except Exception as error:  # noqa: BLE001 — exit-time cleanup must never raise
            cls.logger.debug(f"atexit client close skipped: {error!r}")

    @classmethod
    def chat(
        cls,
        *,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float,
        max_tokens: int | None,
        timeout: float,
        seed: int | None,
        max_retries: int,
    ) -> ChatOpenAI:
        """
        Return a pooled ChatOpenAI for this construction identity, creating it on first use.

        The per-call UsageAccumulator is NOT an argument here: pass it to ``ainvoke`` as a callback so
        the shared client is reused while usage stays attributed per call.

        Args:
            base_url (str): The chat endpoint the client is bound to.
            api_key (str): The resolved credential (the empty-key placeholder already applied upstream).
            model (str): The chat model id.
            temperature (float): Sampling temperature.
            max_tokens (int | None): Generation cap (None = endpoint default).
            timeout (float): Per-request timeout in seconds.
            seed (int | None): Sampling seed when pinned (None = unpinned).
            max_retries (int): The SDK retry count (already resolved: 0 when the caller owns its loop).

        Returns:
            ChatOpenAI: The cached client (a fresh one is created when absent or found closed).
        """
        cls.__ensure_atexit()
        key: _ChatKey = (
            base_url,
            api_key,
            model,
            temperature,
            max_tokens,
            timeout,
            seed,
            max_retries,
        )
        client = cls._chat_clients.get(key)
        if client is None or cls.__is_closed(client):
            client = ChatOpenAI(
                base_url=base_url,
                api_key=api_key,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                seed=seed,
                max_retries=max_retries,
            )
            cls._chat_clients[key] = client
        return client

    @classmethod
    def embeddings(
        cls,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float,
        max_retries: int,
    ) -> OpenAIEmbeddings:
        """
        Return a pooled OpenAIEmbeddings for this construction identity, creating it on first use.

        Args:
            base_url (str): The embeddings endpoint the client is bound to.
            api_key (str): The resolved credential (the empty-key placeholder already applied upstream).
            model (str): The embedding model id.
            timeout (float): Per-request timeout in seconds.
            max_retries (int): The SDK retry count (already resolved: 0 when the caller owns its loop).

        Returns:
            OpenAIEmbeddings: The cached client (a fresh one is created when absent or found closed).
        """
        cls.__ensure_atexit()
        key: _EmbedKey = (base_url, api_key, model, timeout, max_retries)
        client = cls._embed_clients.get(key)
        if client is None or cls.__is_closed(client):
            client = OpenAIEmbeddings(
                base_url=base_url,
                api_key=api_key,
                model=model,
                timeout=timeout,
                max_retries=max_retries,
                check_embedding_ctx_length=False,
            )
            cls._embed_clients[key] = client
        return client

    @classmethod
    async def shutdown(cls) -> None:
        """Close every pooled client's transport and clear the registry (from the lifespan / atexit)."""
        for client in list(cls._chat_clients.values()) + list(cls._embed_clients.values()):
            underlying = cls.__underlying(client)
            close = getattr(underlying, "close", None)
            if not callable(close):
                continue
            try:
                await close()
            except Exception as error:  # noqa: BLE001 — one stuck client must not block the rest
                cls.logger.debug(f"pooled client close skipped: {error!r}")
        cls._chat_clients.clear()
        cls._embed_clients.clear()

    @classmethod
    def reset(cls) -> None:
        """Drop all cached clients WITHOUT awaiting — test isolation only (no transport to close)."""
        cls._chat_clients.clear()
        cls._embed_clients.clear()


__all__ = ["LangChainClientPool"]
