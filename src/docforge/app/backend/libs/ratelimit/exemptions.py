# ====== Code Summary ======
# RateLimitExemptions — decides which request paths the limiter enforces. Only ``/api/v1/*`` is ever
# limited (everything else — the health probe, /metrics, scalar docs, /openapi.json, the static
# frontend — passes untouched). Within /api/v1, the high-frequency job monitoring subtree (the live
# SSE stream + the UI's job / queue / worker polls) is EXEMPT so a normal UI session, which polls those
# routes on a tight interval, never trips the limit.

# ====== Standard Library Imports ======
from __future__ import annotations

# Only the API surface is rate-limited; everything outside it is inherently exempt.
_API_PREFIX = "/api/v1"

# Sub-trees under /api/v1 that the UI polls / streams at high frequency — never rate-limited. The
# whole /api/v1/jobs tree covers the live SSE stream, the job list/detail polls, and the
# queue-depth / workers-live / stage-duration / cost monitoring reads.
_EXEMPT_PREFIXES: tuple[str, ...] = ("/api/v1/jobs",)


class RateLimitExemptions:
    """Static helper deciding whether a path is subject to rate limiting."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("RateLimitExemptions is a static-only class and cannot be instantiated.")

    @staticmethod
    def is_limited(path: str) -> bool:
        """
        Decide whether a request path is subject to the rate limiter.

        Args:
            path (str): The request path (``scope["path"]``).

        Returns:
            bool: True when the path must be rate-limited, False when it is exempt.
        """
        # 1. Only the API surface is limited — health, /metrics, docs and the static UI are exempt.
        if not path.startswith(_API_PREFIX):
            return False

        # 2. The high-frequency job monitoring subtree (poll + SSE) is exempt.
        for prefix in _EXEMPT_PREFIXES:
            if path == prefix or path.startswith(f"{prefix}/"):
                return False

        # 3. Everything else under /api/v1 is limited.
        return True


__all__ = ["RateLimitExemptions"]
