# ====== Code Summary ======
# RateLimitKeyResolver — derives the rate-limit bucket key for one request. When auth is ON the
# caller is keyed by its API key id (per-tenant fairness, stable across the caller's IPs); when auth
# is OFF there is no identity, so it keys by client IP, honouring the leftmost X-Forwarded-For hop
# when the deployment trusts its reverse proxy to set it.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus
from starlette.types import Scope

# ====== Local Project Imports ======
from ..auth import AuthPrincipal


class RateLimitKeyResolver:
    """Static helper that maps a request to its rate-limit bucket key (identity or IP)."""

    logger = loggerplusplus.bind(identifier="RateLimitKeyResolver")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("RateLimitKeyResolver is a static-only class and cannot be instantiated.")

    @staticmethod
    def resolve(scope: Scope, principal: AuthPrincipal | None, trust_forwarded_for: bool) -> str:
        """
        Return the bucket key for a request — the API key id when authenticated, else the client IP.

        Args:
            scope (Scope): The ASGI connection scope (source of client + headers).
            principal (AuthPrincipal | None): The principal injected by the authN middleware, or None
                when it did not run (a non-``/api/v1`` path — never rate-limited anyway).
            trust_forwarded_for (bool): Whether to key IP callers off the leftmost X-Forwarded-For hop.

        Returns:
            str: A stable bucket key (``key:<uuid>`` for an authenticated caller, else ``ip:<addr>``).
        """
        # 1. An authenticated key → key by its stable id (fair per tenant, independent of IP).
        if principal is not None and principal.key is not None:
            return f"key:{principal.key.id}"

        # 2. No identity (auth off / synthetic root) → key by the resolved client IP.
        return f"ip:{RateLimitKeyResolver.client_ip(scope, trust_forwarded_for)}"

    @staticmethod
    def client_ip(scope: Scope, trust_forwarded_for: bool) -> str:
        """
        Resolve the caller's IP — the leftmost trusted X-Forwarded-For hop, else the transport peer.

        Args:
            scope (Scope): The ASGI connection scope.
            trust_forwarded_for (bool): Whether the X-Forwarded-For header may be trusted.

        Returns:
            str: The caller's IP address, or ``"unknown"`` when no peer is present.
        """
        # 1. Behind a trusted proxy, the real client is the leftmost X-Forwarded-For hop.
        if trust_forwarded_for:
            forwarded = RateLimitKeyResolver._header(scope, b"x-forwarded-for")
            if forwarded:
                first = forwarded.split(",")[0].strip()
                if first:
                    return first

        # 2. Otherwise (or when XFF is absent) fall back to the transport peer address.
        client = scope.get("client")
        return client[0] if client else "unknown"

    @staticmethod
    def _header(scope: Scope, name: bytes) -> str | None:
        """
        Read one header value from the raw ASGI header list (case-insensitive byte match).

        Args:
            scope (Scope): The ASGI connection scope.
            name (bytes): The lower-case header name to look up.

        Returns:
            str | None: The decoded header value, or None when the header is absent.
        """
        # 1. ASGI headers are a list of lower-cased (name, value) byte tuples.
        for key, value in scope.get("headers", []):
            if key == name:
                return value.decode("latin-1")
        return None


__all__ = ["RateLimitKeyResolver"]
