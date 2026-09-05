# ====== Code Summary ======
# ScopedSdkProvider resolves the docforge_sdk.AsyncClient to use for the CURRENT call, keyed by
# the caller's DocForge API token (token_context.py). One dedicated client per distinct token is
# created lazily and cached, so the httpx connection pool is reused across calls sharing a token —
# but never mutated/shared ACROSS tokens (that would race under concurrent HTTP requests from
# different callers: a header mutated on a shared client can be overwritten mid-flight by another
# in-flight request). The cache is bounded and evicts LEAST-RECENTLY-USED (an `OrderedDict`, moved
# to the end on every hit) rather than oldest-inserted, so a hot token's client survives a burst of
# distinct cold tokens. Evicted clients are closed via a tracked background task (held in
# `_pending_closes` with a logging done-callback) instead of an unreferenced fire-and-forget task,
# so the close always runs to completion and a close failure is observed, not swallowed by the GC.
#
# The fallback client (built from the env DOCFORGE_API_TOKEN) is ONLY resolved for the stdio
# transport (`require_bearer=False`) — the local, single-caller, no-network case where there is no
# Authorization header to forward. In HTTP mode (`require_bearer=True`) a missing context token
# raises MissingBearerTokenError instead of silently granting the fallback token's rights: in
# practice this never triggers in production because BearerPassthroughMiddleware (auth.py) already
# rejects a bearer-less HTTP request with 401 before any tool call resolves an SDK client — this is
# the defense-in-depth backstop for that invariant, not the primary enforcement point.
#
# ScopedSdk is the thin proxy actually injected into the tools: its __getattr__ forwards every
# attribute access (`.search`, `.collections`, ...) to the provider's CURRENT client, so no tool
# file or its signature changes — they keep calling `sdk.<resource>.<method>(...)` and
# transparently get the right token's client at call time.

from __future__ import annotations

# ====== Standard Library Imports ======
import asyncio
from collections import OrderedDict
from typing import Any

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .token_context import incoming_docforge_token

# Bound above this, the least-recently-used cached per-token client is evicted (and closed) so a
# stream of distinct/garbage bearer tokens (e.g. an attacker probing the endpoint) cannot grow the
# cache unbounded. Comfortably above any realistic number of concurrent DocForge API keys in use.
_MAX_CACHED_CLIENTS = 64


class MissingBearerTokenError(RuntimeError):
    """
    Raised by ``ScopedSdkProvider.current`` when running with ``require_bearer=True`` (HTTP
    transport) and the current call has no caller token in context.

    This must never happen in a running server: ``BearerPassthroughMiddleware`` rejects a
    bearer-less HTTP request with 401 before any tool call reaches the SDK client selection. Its
    only job is to make sure that IF that invariant is ever bypassed (a wiring mistake, a future
    code path), the failure is loud and denies access rather than silently granting the fallback
    (local, potentially root-scoped) token's rights.
    """


class ScopedSdkProvider(LoggerClass):
    """Owns one AsyncClient per distinct caller token, plus the env-token fallback client."""

    def __init__(
        self, base_url: str, timeout: float, fallback_token: str, *, require_bearer: bool
    ) -> None:
        """
        Build the fallback client; per-token clients are created lazily on first use.

        Args:
            base_url (str): The DocForge API origin.
            timeout (float): Per-request timeout in seconds, shared by every client.
            fallback_token (str): DOCFORGE_API_TOKEN — used only when ``require_bearer`` is False.
            require_bearer (bool): True for the streamable-HTTP transport, where every call MUST
                have a caller token in context — ``current`` raises instead of falling back. False
                for stdio, where the fallback token is the intended, sole credential.
        """
        LoggerClass.__init__(self)
        self._base_url = base_url
        self._timeout = timeout
        self._require_bearer = require_bearer
        self._fallback_client = AsyncClient(base_url, timeout=timeout, api_token=fallback_token)
        # Insertion order = recency order: moved to the end on every cache hit, so the front is
        # always the least-recently-used entry (see `_client_for_token`).
        self._by_token: OrderedDict[str, AsyncClient] = OrderedDict()
        # Strong references to in-flight eviction close() tasks, so they cannot be garbage
        # collected mid-close; each is removed from this set by its own done-callback.
        self._pending_closes: set[asyncio.Task[None]] = set()

    @property
    def current(self) -> AsyncClient:
        """
        Resolve the client for the token stashed in the current request's context (if any).

        Returns:
            AsyncClient: The caller-scoped client, or (stdio only) the fallback client when the
                context carries no token.

        Raises:
            MissingBearerTokenError: ``require_bearer`` is True (HTTP transport) and the context
                carries no caller token — see the class docstring for why this is a backstop, not
                the primary enforcement point.
        """
        token = incoming_docforge_token.get()
        if token:
            return self._client_for_token(token)
        if self._require_bearer:
            raise MissingBearerTokenError(
                "No caller bearer token in context while running with require_bearer=True; the "
                "request should have been rejected by BearerPassthroughMiddleware before reaching "
                "this point."
            )
        return self._fallback_client

    async def aclose(self) -> None:
        """Close the fallback client, every cached per-token client, and any pending eviction."""
        await self._fallback_client.aclose()
        for client in self._by_token.values():
            await client.aclose()
        if self._pending_closes:
            await asyncio.gather(*self._pending_closes, return_exceptions=True)

    def _client_for_token(self, token: str) -> AsyncClient:
        """
        Get or lazily create the cached client for one caller token.

        Args:
            token (str): The caller's DocForge API key.

        Returns:
            AsyncClient: The cached (or newly built) client scoped to that token.
        """
        # 1. Reuse the pooled client when this token has already been seen, marking it
        #    most-recently-used so it survives the next eviction.
        client = self._by_token.get(token)
        if client is not None:
            self._by_token.move_to_end(token)
            return client

        # 2. First time this token is used — evict the least-recently-used entry once the cache
        #    is full so it cannot grow unbounded, then build and cache a dedicated client for it.
        if len(self._by_token) >= _MAX_CACHED_CLIENTS:
            _, lru_client = self._by_token.popitem(last=False)
            self.logger.warning(
                f"Evicting cached SDK client (cache size hit {_MAX_CACHED_CLIENTS})"
            )
            self._schedule_close(lru_client)

        client = AsyncClient(self._base_url, timeout=self._timeout, api_token=token)
        self._by_token[token] = client
        return client

    def _schedule_close(self, client: AsyncClient) -> None:
        """
        Close an evicted client in the background without ever losing track of the task.

        This method is a sync cache lookup, but it always runs inside a tool's running event
        loop, so scheduling a task is safe. Unlike a bare ``asyncio.create_task(...)`` whose
        return value is discarded, the task is held in ``_pending_closes`` (so it cannot be
        garbage-collected before completion) and its done-callback logs any exception raised by
        ``aclose()`` instead of leaving it unobserved, then removes the task from the set.

        Args:
            client (AsyncClient): The evicted client to close.
        """
        task = asyncio.create_task(client.aclose())
        self._pending_closes.add(task)

        def _on_done(finished: asyncio.Task[None]) -> None:
            self._pending_closes.discard(finished)
            error = finished.exception() if not finished.cancelled() else None
            if error is not None:
                self.logger.error(f"Failed to close evicted SDK client: {error!r}")

        task.add_done_callback(_on_done)


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


__all__ = ["MissingBearerTokenError", "ScopedSdk", "ScopedSdkProvider"]
