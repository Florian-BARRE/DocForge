# ====== Code Summary ======
# Static helpers for RequestIdMiddleware: resolve the request's correlation id from the inbound
# headers (honouring an upstream proxy/gateway's id) and sanitise it. A correlation id is echoed back
# in a RESPONSE header and stamped into logs, so an untrusted inbound value is constrained to a safe
# charset + length — a client must never be able to inject CR/LF (header splitting) or unbounded junk.

from __future__ import annotations

# ====== Standard Library Imports ======
import re

# ====== Internal Project Imports ======
from shared_libs.observability import CorrelationContext

# Inbound headers honoured, in priority order: the de-facto standard `X-Request-ID` first, then
# `X-Correlation-ID` as an accepted alias. The first that yields a valid value wins.
_INBOUND_HEADERS: tuple[str, ...] = ("x-request-id", "x-correlation-id")
# A conservative safe charset for an id that will ride back out in a header and into log lines.
_SAFE_ID = re.compile(r"[^A-Za-z0-9._\-]")
# Hard cap so an inbound id can never bloat a log line or a response header.
_MAX_LENGTH = 128


class RequestIdHelpers:
    """Static-only helpers for resolving and sanitising the request correlation id."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("RequestIdHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    def resolve(cls, headers: list[tuple[bytes, bytes]]) -> str:
        """
        Return the correlation id for this request — the inbound one when valid, else a fresh id.

        Args:
            headers (list[tuple[bytes, bytes]]): The raw ASGI header pairs (lower-cased names).

        Returns:
            str: A sanitised inbound id (preserving an upstream proxy's id end-to-end), or a newly
                minted id when no honoured header carries a usable value.
        """
        # 1. Index the honoured inbound headers (first occurrence wins) as decoded strings.
        seen: dict[str, str] = {}
        for raw_name, raw_value in headers:
            name = raw_name.decode("latin-1").lower()
            if name in _INBOUND_HEADERS and name not in seen:
                seen[name] = raw_value.decode("latin-1")

        # 2. Take the first honoured header that sanitises to a non-empty id.
        for name in _INBOUND_HEADERS:
            if name in seen:
                candidate = cls._sanitise(seen[name])
                if candidate:
                    return candidate

        # 3. Nothing usable inbound → mint a fresh id.
        return CorrelationContext.generate()

    @classmethod
    def _sanitise(cls, value: str) -> str:
        """
        Strip an inbound id to the safe charset and cap its length.

        Args:
            value (str): The raw inbound header value.

        Returns:
            str: The sanitised id (possibly empty when the input held no safe characters).
        """
        # 1. Drop every character outside the safe set (kills CR/LF and other header-splitting bytes).
        cleaned = _SAFE_ID.sub("", value.strip())

        # 2. Bound the length so a hostile client cannot bloat logs/headers.
        return cleaned[:_MAX_LENGTH]


__all__ = ["RequestIdHelpers"]
