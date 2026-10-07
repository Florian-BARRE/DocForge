# ====== Code Summary ======
# ProviderLimiter — the pure-engine seam through which a node asks "may I have an in-flight slot
# against this provider endpoint?". The engine ships only the interface, the no-op default and the
# process-wide registry; the REAL implementation (a Redis lease semaphore shared by every worker
# process) lives at the worker edge and is installed at startup. A node never imports Redis: it calls
# ``ProviderLimiterRegistry.current().slot(...)``. Unbound (unit tests, the app's search path, a
# deployment with the limiter disabled) resolves to the no-op, so behaviour is unchanged.

# ====== Standard Library Imports ======
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from urllib.parse import urlsplit

_DEFAULT_PORTS = {"http": 80, "https": 443}


class EndpointKey:
    """Normalises a provider ``base_url`` to the stable identity its capacity is shared under."""

    @staticmethod
    def normalize(base_url: str) -> str:
        """
        Reduce a base URL to ``scheme://host:port`` (lower-cased, default port made explicit).

        The path is dropped on purpose: ``https://api.x.com/v1`` and ``https://api.x.com/v2`` are the
        same machine, so they share one capacity budget — as do two collections pointing at the same
        shared embedder through differently-spelled URLs (trailing slash, upper-case host, implicit port).

        Args:
            base_url (str): The provider URL as configured on the node.

        Returns:
            str: The normalised endpoint identity (the raw stripped string if it is not a valid URL).
        """
        parts = urlsplit(base_url.strip())
        if not parts.scheme or not parts.hostname:
            return base_url.strip().lower().rstrip("/")
        scheme = parts.scheme.lower()
        port = parts.port or _DEFAULT_PORTS.get(scheme)
        return (
            f"{scheme}://{parts.hostname.lower()}:{port}"
            if port
            else f"{scheme}://{parts.hostname.lower()}"
        )


class ProviderSlotTimeout(Exception):
    """No in-flight slot was granted on an endpoint within the limiter's wait budget.

    Raised INSTEAD of proceeding without a slot: proceeding would disable the cap exactly when the
    shared provider is overloaded. A caller treats it like a provider timeout (retry with backoff) but
    must never split the batch on it — smaller requests only queue behind the same saturated endpoint.
    Deliberately NOT a ``TimeoutError`` (an ``OSError``): the limiter fails open on OS/Redis errors,
    and this verdict must never be mistaken for one.
    """


class ProviderLimiter(ABC):
    """Caps concurrent in-flight requests to one provider endpoint (across processes if distributed)."""

    @abstractmethod
    def slot(
        self, endpoint: str, *, max_inflight: int | None = None, lease_seconds: float = 60.0
    ) -> AbstractAsyncContextManager[None]:
        """
        Hold one in-flight slot on ``endpoint`` for the duration of the ``async with`` body.

        Args:
            endpoint (str): The normalised endpoint identity (see ``EndpointKey.normalize``).
            max_inflight (int | None): Per-call cap override; None → the limiter's own default.
            lease_seconds (float): Upper bound the slot may be held before it expires on its own
                (a crashed holder must never pin a slot forever). Callers pass their request timeout
                plus a margin.

        Returns:
            AbstractAsyncContextManager[None]: Released on exit — except when the body raised after
                its request reached the provider (a client timeout / mid-request transport error):
                the abandoned request keeps the provider busy, so its slot is left to expire.

        Raises:
            ProviderSlotTimeout: No slot was granted within the limiter's wait budget.
        """


class NoOpProviderLimiter(ProviderLimiter):
    """The default when nothing is installed: every slot is granted instantly."""

    @asynccontextmanager
    async def slot(
        self, endpoint: str, *, max_inflight: int | None = None, lease_seconds: float = 60.0
    ) -> AsyncIterator[None]:
        """Grant immediately; nothing to release."""
        _ = (endpoint, max_inflight, lease_seconds)
        yield


class ProviderLimiterRegistry:
    """Process-wide holder of the active limiter — installed once at the worker edge."""

    _active: ProviderLimiter = NoOpProviderLimiter()

    @classmethod
    def current(cls) -> ProviderLimiter:
        """The installed limiter, or the no-op default."""
        return cls._active

    @classmethod
    def install(cls, limiter: ProviderLimiter) -> None:
        """Install the process-wide limiter (worker startup)."""
        cls._active = limiter

    @classmethod
    def reset(cls) -> None:
        """Restore the no-op default (worker shutdown, test isolation)."""
        cls._active = NoOpProviderLimiter()


__all__ = [
    "EndpointKey",
    "ProviderLimiter",
    "ProviderSlotTimeout",
    "NoOpProviderLimiter",
    "ProviderLimiterRegistry",
]
