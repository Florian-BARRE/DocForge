# ====== Code Summary ======
# HttpClientPool — a process-wide pool of httpx.AsyncClient instances shared by every raw-httpx
# node (bge_server embed, gotenberg convert/preview, mistral/paddle OCR, the sidecar parsers).
# Each node used to open a NEW client (socket + TLS handshake) inside its retried POST closure, so a
# fresh connection was paid per batch, per item AND per retry attempt — worst on bge_server, the
# default embedder. The pool caches one client per connection identity (base_url, timeout, auth,
# headers) so retries and successive calls REUSE the kept-alive connection. A node stays pure: a
# pooled HTTP client is a provider-connection resource, never DB/S3 I/O. One event loop per process
# (worker / app search) makes a loop-bound cached client safe; a client found closed is recreated
# defensively. A close-all runs at process exit (atexit) and via the explicit shutdown() the
# worker/app lifespan calls, so no connection leaks on an orderly stop.
#
# Restart resilience: a kept-alive connection survives its endpoint (a sidecar restart leaves the
# pooled client holding a DEAD socket to the gone container — the next call raises a connect-phase
# error even though the service is back up). ``run()`` wraps a caller operation and, on a
# connect-phase error ONLY, evicts + recreates the pooled client and retries the operation once on a
# fresh one (DNS re-resolved, new socket). A connect-phase failure guarantees no byte reached the
# server, so replaying the operation is idempotency-safe even for a non-idempotent POST — see run().

# ====== Standard Library Imports ======
import asyncio
import atexit
from collections.abc import Awaitable, Callable
from typing import TypeVar

# ====== Third-Party Library Imports ======
import httpx
from loggerplusplus import loggerplusplus

_Result = TypeVar("_Result")

# Connect-phase httpx errors: the connection was never established, so NO request byte reached the
# server. Only these are safe to auto-replay (see run()); a ReadError/WriteError/RemoteProtocolError
# means bytes MAY have been sent and a non-idempotent POST must NOT be blindly replayed here.
_CONNECT_ERRORS: tuple[type[Exception], ...] = (httpx.ConnectError, httpx.ConnectTimeout)

# The cache key: the bits that define a distinct kept-alive connection — endpoint, timeout, and the
# auth/header reprs (two callers with different credentials must never share a client).
_PoolKey = tuple[str, float, str, str]


class HttpClientPool:
    """Process-wide registry of reusable httpx.AsyncClient instances, keyed by connection identity."""

    logger = loggerplusplus.bind(identifier="HttpClientPool")
    _clients: dict[_PoolKey, httpx.AsyncClient] = {}
    _atexit_registered: bool = False

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("HttpClientPool is a static-only class and cannot be instantiated.")

    @staticmethod
    def __key(
        base_url: str,
        timeout: float,
        auth: httpx.Auth | None,
        headers: dict[str, str] | None,
    ) -> _PoolKey:
        """Build the cache key from the connection-defining bits (stable, hashable reprs)."""
        header_repr = repr(sorted((headers or {}).items()))
        return (base_url, timeout, repr(auth), header_repr)

    @classmethod
    def __ensure_atexit(cls) -> None:
        """Register the process-exit close-all exactly once (lazy, on first client creation)."""
        if not cls._atexit_registered:
            atexit.register(cls.__atexit_close)
            cls._atexit_registered = True

    @classmethod
    def __atexit_close(cls) -> None:
        """Best-effort synchronous close-all at interpreter exit (no running loop expected here)."""
        if not cls._clients:
            return
        try:
            asyncio.run(cls.shutdown())
        except Exception as error:  # noqa: BLE001 — exit-time cleanup must never raise
            cls.logger.debug(f"atexit client close skipped: {error!r}")

    @classmethod
    def get(
        cls,
        *,
        base_url: str,
        timeout: float,
        auth: httpx.Auth | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.AsyncClient:
        """
        Return a pooled httpx.AsyncClient for this connection identity, creating it on first use.

        Must be called OUTSIDE a retry loop so every attempt reuses the one kept-alive connection —
        that reuse is the whole point. Request-specific bits (route, json/files/content, per-call
        headers, query params) are passed to ``.post(...)``, not here; only the connection-defining
        ``base_url``/``timeout``/``auth``/``headers`` shape the client (and the cache key).

        Args:
            base_url (str): The provider endpoint the client is bound to.
            timeout (float): Per-request timeout in seconds.
            auth (httpx.Auth | None): Client-level auth (e.g. a remote Gotenberg's basic auth).
            headers (dict[str, str] | None): Client-level default headers, if any.

        Returns:
            httpx.AsyncClient: The cached client (a fresh one is created when absent or closed).
        """
        # 1. Register the exit hook lazily — only once any client actually exists.
        cls.__ensure_atexit()

        # 2. Look the client up by connection identity; recreate if absent or defensively closed
        #    (a client cached on a now-closed event loop reports closed and must not be reused).
        key = cls.__key(base_url, timeout, auth, headers)
        client = cls._clients.get(key)
        if client is None or getattr(client, "is_closed", False):
            client = httpx.AsyncClient(
                base_url=base_url, timeout=timeout, auth=auth, headers=headers or None
            )
            cls._clients[key] = client
        return client

    @classmethod
    async def __evict(
        cls,
        base_url: str,
        timeout: float,
        auth: httpx.Auth | None,
        headers: dict[str, str] | None,
    ) -> None:
        """Drop the pooled client for this identity and best-effort close its (dead) socket."""
        client = cls._clients.pop(cls.__key(base_url, timeout, auth, headers), None)
        if client is None:
            return
        try:
            await client.aclose()
        except Exception as error:  # noqa: BLE001 — the socket is already dead; closing is best-effort
            cls.logger.debug(f"evicted client close skipped: {error!r}")

    @classmethod
    async def run(
        cls,
        operation: Callable[[httpx.AsyncClient], Awaitable[_Result]],
        *,
        base_url: str,
        timeout: float,
        auth: httpx.Auth | None = None,
        headers: dict[str, str] | None = None,
    ) -> _Result:
        """
        Run ``operation(client)`` on the pooled client, self-healing a dead pooled connection.

        On a CONNECT-PHASE error (``ConnectError``/``ConnectTimeout`` — a sidecar that restarted
        leaves the pooled client holding a dead keep-alive socket), the stale client is evicted and
        recreated and the operation is retried ONCE on a fresh client (DNS re-resolved, new socket).
        A connect-phase failure means the connection was never established, hence NO request byte
        reached the server — replaying is idempotency-safe even for a non-idempotent POST. Any other
        error (read/write/protocol/status) may follow a partially-sent request and is re-raised as-is,
        NOT replayed here; the caller's own bounded retry decides what is safe to repeat.

        Args:
            operation (Callable[[httpx.AsyncClient], Awaitable]): The async call to run against the
                pooled client (request-specific route/body/headers stay inside this closure).
            base_url (str): The provider endpoint the client is bound to.
            timeout (float): Per-request timeout in seconds.
            auth (httpx.Auth | None): Client-level auth (part of the connection identity).
            headers (dict[str, str] | None): Client-level default headers (part of the identity).

        Returns:
            The operation's result — from the first attempt, or from the retry on a fresh client.

        Raises:
            Exception: The connect-phase error if the retry on a fresh client also fails, or any
                non-connect error unchanged (never auto-replayed).
        """
        # 1. Run on the pooled (possibly kept-alive) client.
        client = cls.get(base_url=base_url, timeout=timeout, auth=auth, headers=headers)
        try:
            return await operation(client)
        except _CONNECT_ERRORS as error:
            # 2. Dead socket to a gone/restarting endpoint — evict, recreate, retry exactly once.
            cls.logger.warning(
                f"pooled connection to {base_url} is dead ({error!r}); evicting and retrying "
                f"once on a fresh client"
            )
            await cls.__evict(base_url, timeout, auth, headers)
            fresh = cls.get(base_url=base_url, timeout=timeout, auth=auth, headers=headers)
            return await operation(fresh)

    @classmethod
    async def shutdown(cls) -> None:
        """Close every pooled client and clear the registry (called from the lifespan / atexit)."""
        for client in list(cls._clients.values()):
            try:
                await client.aclose()
            except Exception as error:  # noqa: BLE001 — one stuck client must not block the rest
                cls.logger.debug(f"pooled client close skipped: {error!r}")
        cls._clients.clear()

    @classmethod
    def reset(cls) -> None:
        """Drop all cached clients WITHOUT awaiting — test isolation only (no connection to close)."""
        cls._clients.clear()


__all__ = ["HttpClientPool"]
