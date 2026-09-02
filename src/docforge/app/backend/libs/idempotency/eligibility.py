# ====== Code Summary ======
# IdempotencyEligibility — the explicit allow-list of endpoints the Idempotency-Key middleware guards,
# and the matcher that maps a concrete request (method + raw path) to its low-cardinality route
# TEMPLATE. ONLY small-JSON-body mutating triggers are eligible: create/update collection, the two
# reingest triggers, and export. The large multipart uploads — document ingest and the import-bundle
# upload — are DELIBERATELY absent (buffering a multi-GB body to fingerprint + replay would blow memory
# and break S3 streaming, and uploads are already content-addressed by sha256, so idempotency there is
# both unsafe and redundant). The API-key create/rotate routes are ALSO deliberately absent: their
# response carries the ONE-TIME plaintext secret ("shown once, never stored"), and caching a response
# body would persist that secret at rest for the TTL — a redacted cache can't serve a real retry
# either, so response-body idempotency simply cannot apply to secret-returning routes.
#
# The matcher runs at the ASGI layer BEFORE routing, so ``scope["route"]`` is not yet populated —
# hence the middleware cannot read the template off the resolved route and instead matches the raw
# path against these compiled patterns itself. The returned template is exactly what would later
# become ``scope["route"].path`` and is what the store persists as the low-cardinality ``path``.

# ====== Standard Library Imports ======
from __future__ import annotations

import re

# The eligible (method, route TEMPLATE) pairs — the ONLY endpoints idempotency engages on. Kept as
# an explicit tuple (not derived from the router) so adding a route to the app never silently opts it
# into response buffering; a new eligible endpoint is a conscious edit here.
_ELIGIBLE_ROUTES: tuple[tuple[str, str], ...] = (
    # Create a collection (small JSON contract body).
    ("POST", "/api/v1/collections"),
    # Update / patch a collection (small JSON contract body).
    ("PATCH", "/api/v1/collections/{collection_id}"),
    # Trigger a whole-collection reingest (small JSON body).
    ("POST", "/api/v1/collections/{collection_id}/reingest"),
    # Trigger a selector-scoped bulk reingest (small JSON selector body).
    ("POST", "/api/v1/collections/{collection_id}/documents/reingest"),
    # Trigger an async collection export (no body — a pure trigger).
    ("POST", "/api/v1/collections/{collection_id}/export"),
)


def _compile(template: str) -> re.Pattern[str]:
    """
    Compile one route TEMPLATE into an anchored regex matching a concrete path.

    Args:
        template (str): The route template, e.g. ``/api/v1/collections/{collection_id}``.

    Returns:
        re.Pattern[str]: A full-match pattern where each ``{param}`` matches one path segment.
    """
    # 1. Replace each {param} placeholder with a single-segment matcher, escaping the literal parts.
    parts = re.split(r"\{[^/}]+\}", template)
    pattern = "[^/]+".join(re.escape(part) for part in parts)
    return re.compile(rf"^{pattern}$")


# Pre-compiled (method, pattern, template) triples — compiled once at import so per-request matching
# is a cheap linear scan over a handful of anchored patterns.
_COMPILED: tuple[tuple[str, re.Pattern[str], str], ...] = tuple(
    (method, _compile(template), template) for method, template in _ELIGIBLE_ROUTES
)


class IdempotencyEligibility:
    """Static matcher mapping an eligible mutating request to its route TEMPLATE (else None)."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("IdempotencyEligibility is a static-only class and cannot be instantiated.")

    @staticmethod
    def match(method: str, path: str) -> str | None:
        """
        Return the route TEMPLATE an eligible request maps to, or None when it is not eligible.

        Args:
            method (str): The request's HTTP method.
            path (str): The raw request path (``scope["path"]``, no query string).

        Returns:
            str | None: The matched route template (the low-cardinality ``path`` the store persists),
                or None when the (method, path) pair is not in the eligible allow-list.
        """
        # 1. Linear scan over the compiled allow-list — return the first template whose method and
        #    anchored pattern both match. The set is tiny, so this is effectively O(1).
        for candidate_method, pattern, template in _COMPILED:
            if candidate_method == method and pattern.match(path):
                return template
        return None


__all__ = ["IdempotencyEligibility"]
