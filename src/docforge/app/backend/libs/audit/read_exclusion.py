# ====== Code Summary ======
# AuditReadExclusion — the explicit allow-list of POST-shaped READ endpoints the audit trail must NOT
# record. The audit contract is "reads are never audited", but that rule was enforced purely by HTTP
# VERB (GET/HEAD/OPTIONS), so a handful of genuinely read-only endpoints exposed over POST (they carry
# a JSON body the query needs) leaked into the trail. These are pure query / compute endpoints: they
# change NO state, enqueue NO job, and are guarded by the READ (or SEARCH) capability. They are
# distinguished here by an explicit template allow-list — NOT by capability — because capability is not
# a clean mutation signal (e.g. collection EXPORT is a READ-capability endpoint that DOES create a
# transfer job, so it must stay audited and is deliberately absent below).
#
# The matcher runs at the ASGI layer BEFORE routing (the audit gate decides applicability up front, so
# a read passes straight through with zero added work), so ``scope["route"]`` is not yet populated —
# each route TEMPLATE is compiled to an anchored regex matched against the raw path, exactly like the
# idempotency eligibility matcher.

# ====== Standard Library Imports ======
from __future__ import annotations

import re

# The POST-shaped READ route TEMPLATES excluded from auditing — pure query/compute, no state change,
# no job. Export/import (which DO create transfer jobs) are intentionally NOT here → they stay audited.
_READ_ROUTES: tuple[str, ...] = (
    # Hybrid search over a collection (pure retrieval).
    "/api/v1/collections/{collection_id}/search",
    # Server-side document-grid query (pure filtered read).
    "/api/v1/collections/{collection_id}/documents/query",
    # Pre-hoc cost estimate (pure projection — no job enqueued, nothing spent).
    "/api/v1/collections/{collection_id}/estimate",
    # Pipeline design surfaces — all pure graph compute over a body-supplied blob, nothing persisted.
    "/api/v1/pipelines/{key}/inspect",
    "/api/v1/pipelines/{key}/edit",
    "/api/v1/pipelines/{key}/stages/view",
    "/api/v1/pipelines/{key}/stages/apply",
)


def _compile(template: str) -> re.Pattern[str]:
    """
    Compile one route TEMPLATE into an anchored regex matching a concrete path.

    Args:
        template (str): The route template, e.g. ``/api/v1/collections/{collection_id}/search``.

    Returns:
        re.Pattern[str]: A full-match pattern where each ``{param}`` matches one path segment.
    """
    # 1. Replace each {param} placeholder with a single-segment matcher, escaping the literal parts.
    parts = re.split(r"\{[^/}]+\}", template)
    pattern = "[^/]+".join(re.escape(part) for part in parts)
    return re.compile(rf"^{pattern}$")


# Pre-compiled anchored patterns — compiled once at import so the per-request check is a cheap scan.
_COMPILED: tuple[re.Pattern[str], ...] = tuple(_compile(template) for template in _READ_ROUTES)


class AuditReadExclusion:
    """Static matcher flagging a POST-shaped READ endpoint that must be excluded from auditing."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("AuditReadExclusion is a static-only class and cannot be instantiated.")

    @staticmethod
    def is_read(path: str) -> bool:
        """
        Return whether a path is a known POST-shaped READ endpoint (excluded from the audit trail).

        Args:
            path (str): The raw request path (``scope["path"]``, no query string).

        Returns:
            bool: True when the path matches one of the read-only POST templates → do NOT audit.
        """
        # 1. Linear scan over the tiny compiled allow-list — first anchored match wins.
        return any(pattern.match(path) for pattern in _COMPILED)


__all__ = ["AuditReadExclusion"]
