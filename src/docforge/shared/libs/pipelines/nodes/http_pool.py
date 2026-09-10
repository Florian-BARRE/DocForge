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

# ====== Standard Library Imports ======
import asyncio
import atexit

# ====== Third-Party Library Imports ======
import httpx
from loggerplusplus import loggerplusplus

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
