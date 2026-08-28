# ====== Code Summary ======
# ScopedSdkProvider resolves the docforge_sdk.AsyncClient to use for the CURRENT call, keyed by
# the caller's DocForge API token (token_context.py). One dedicated client per distinct token is
# created lazily and cached, so the httpx connection pool is reused across calls sharing a token —
# but never mutated/shared ACROSS tokens (that would race under concurrent HTTP requests from
# different callers: a header mutated on a shared client can be overwritten mid-flight by another
# in-flight request). stdio transport, and any HTTP request without a bearer, always resolve to
# the single fallback client built from the env DOCFORGE_API_TOKEN — today's unchanged behaviour.
#
# ScopedSdk is the thin proxy actually injected into the tools: its __getattr__ forwards every
# attribute access (`.search`, `.collections`, ...) to the provider's CURRENT client, so no tool
# file or its signature changes — they keep calling `sdk.<resource>.<method>(...)` and
# transparently get the right token's client at call time.

from __future__ import annotations

# ====== Standard Library Imports ======
import asyncio
from typing import Any

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .token_context import incoming_docforge_token

# Bound above this, the oldest cached per-token client is evicted (and closed) so a stream of
# distinct/garbage bearer tokens (e.g. an attacker probing the endpoint) cannot grow the cache
# unbounded. Comfortably above any realistic number of concurrent DocForge API keys in use.
_MAX_CACHED_CLIENTS = 64


class ScopedSdkProvider(LoggerClass):
    """Owns one AsyncClient per distinct caller token, plus the env-token fallback client."""

    def __init__(self, base_url: str, timeout: float, fallback_token: str) -> None:
        """
        Build the fallback client; per-token clients are created lazily on first use.

        Args:
            base_url (str): The DocForge API origin.
            timeout (float): Per-request timeout in seconds, shared by every client.
            fallback_token (str): DOCFORGE_API_TOKEN — used for stdio, and for any HTTP request
                that carries no Authorization header.
        """
        LoggerClass.__init__(self)
        self._base_url = base_url
        self._timeout = timeout
        self._fallback_client = AsyncClient(base_url, timeout=timeout, api_token=fallback_token)
        self._by_token: dict[str, AsyncClient] = {}

    @property
    def current(self) -> AsyncClient:
        """
        Resolve the client for the token stashed in the current request's context (if any).

        Returns:
            AsyncClient: The caller-scoped client, or the fallback client outside of an HTTP
                request (stdio) or when the caller sent no Authorization header.
        """
        token = incoming_docforge_token.get()
        if not token:
            return self._fallback_client
        return self._client_for_token(token)

    async def aclose(self) -> None:
        """Close the fallback client and every cached per-token client."""
        await self._fallback_client.aclose()
        for client in self._by_token.values():
            await client.aclose()

    def _client_for_token(self, token: str) -> AsyncClient:
        """
        Get or lazily create the cached client for one caller token.

        Args:
            token (str): The caller's DocForge API key.

        Returns:
            AsyncClient: The cached (or newly built) client scoped to that token.
        """
        # 1. Reuse the pooled client when this token has already been seen.
        client = self._by_token.get(token)
        if client is not None:
            return client

        # 2. First time this token is used — evict the oldest entry once the cache is full so it
        #    cannot grow unbounded, then build and cache a dedicated client for it.
        if len(self._by_token) >= _MAX_CACHED_CLIENTS:
            oldest_token, oldest_client = next(iter(self._by_token.items()))
            del self._by_token[oldest_token]
            self.logger.warning(
                f"Evicting cached SDK client (cache size hit {_MAX_CACHED_CLIENTS})"
            )
            # Best-effort async close in the background — this method is a sync cache lookup, but
            # it always runs inside a tool's running event loop, so a fire-and-forget task is safe.
            asyncio.create_task(oldest_client.aclose())

        client = AsyncClient(self._base_url, timeout=self._timeout, api_token=token)
        self._by_token[token] = client
        return client


class ScopedSdk:
    """
    Duck-typed stand-in for AsyncClient: forwards every attribute to the provider's CURRENT client.

    Injected into build_mcp() via ``typing.cast(AsyncClient, ...)`` at the single construction
    site in entrypoint.py, so every tool file keeps its ``sdk: AsyncClient`` type hint unchanged.
    """

    def __init__(self, provider: ScopedSdkProvider) -> None:
        """
        Args:
            provider (ScopedSdkProvider): The per-token client resolver.
        """
        self._provider = provider

    def __getattr__(self, name: str) -> Any:
        """
        Forward attribute access to the provider's current AsyncClient.

        Args:
            name (str): The attribute name (a resource group, e.g. "search", "collections").

        Returns:
            Any: The matching attribute on the currently-selected AsyncClient.
        """
        return getattr(self._provider.current, name)


__all__ = ["ScopedSdk", "ScopedSdkProvider"]
