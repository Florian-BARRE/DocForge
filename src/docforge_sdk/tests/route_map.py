# ====== Code Summary ======
# Shared source of truth for the route-coverage check: every (METHOD, path) the DocForge backend
# OpenAPI exposes must be either a wired SDK resource method (ROUTES) or an explicit, reasoned
# exemption (EXEMPT_ROUTES) — e.g. an SSE stream the SDK deliberately does not wrap. Paths are written
# using the OpenAPI's own path-parameter names verbatim (e.g. "{collection_id}"), including the
# "/api/v1" prefix every versioned SDK request is mounted under (docforge_sdk/_transport_base.py,
# _API_PREFIX). This is a helper module, not a test module — pytest does not collect it, matching
# parity_map.py's convention.

# Every (HTTP method, path) a docforge_sdk resource method builds a RequestSpec for, one row per public
# resource method in docforge_sdk/resources/ (grouped by resource file below). The bare-origin /health
# probe is deliberately absent: it is registered with include_in_schema=False, so it never appears in
# the OpenAPI document this set is diffed against.
ROUTES: set[tuple[str, str]] = {
    # Audit — resources/audit.py
    ("GET", "/api/v1/audit"),
    # Auth — resources/auth.py
    ("GET", "/api/v1/auth/keys"),
    ("POST", "/api/v1/auth/keys"),
    ("DELETE", "/api/v1/auth/keys/{key_id}"),
    ("POST", "/api/v1/auth/keys/{key_id}/rotate"),
    ("GET", "/api/v1/auth/whoami"),
    # Blobs — resources/blobs.py
    ("GET", "/api/v1/blobs/{content_hash}"),
    # Explorer — resources/explorer.py
    ("PATCH", "/api/v1/chunks/enabled"),
    ("PATCH", "/api/v1/chunks/{chunk_id}/enabled"),
    ("GET", "/api/v1/collections/{collection_id}/documents"),
    ("GET", "/api/v1/documents/{document_id}"),
    ("GET", "/api/v1/documents/{document_id}/pages"),
    ("GET", "/api/v1/documents/{document_id}/ir"),
    ("GET", "/api/v1/documents/{document_id}/provenance"),
    ("GET", "/api/v1/documents/{document_id}/chunks"),
    ("DELETE", "/api/v1/documents/{document_id}"),
    # Collections — resources/collections.py
    ("GET", "/api/v1/collections"),
    ("POST", "/api/v1/collections"),
    ("GET", "/api/v1/collections/contract-schema"),
    ("DELETE", "/api/v1/collections/{collection_id}"),
    ("GET", "/api/v1/collections/{collection_id}"),
    ("PATCH", "/api/v1/collections/{collection_id}"),
    ("GET", "/api/v1/collections/{collection_id}/health"),
    ("GET", "/api/v1/collections/{collection_id}/storage"),
    ("POST", "/api/v1/collections/{collection_id}/reingest"),
    ("POST", "/api/v1/collections/{collection_id}/estimate"),
    # Corpus grid + bulk ops — resources/corpus.py
    ("POST", "/api/v1/collections/{collection_id}/documents/query"),
    ("POST", "/api/v1/collections/{collection_id}/documents/delete"),
    ("POST", "/api/v1/collections/{collection_id}/documents/set-enabled"),
    ("POST", "/api/v1/collections/{collection_id}/documents/reingest"),
    # Documents (upload / toggle / reingest / rendered views) — resources/documents.py
    ("POST", "/api/v1/documents"),
    ("PATCH", "/api/v1/documents/{document_id}/enabled"),
    ("POST", "/api/v1/documents/{document_id}/reingest"),
    ("GET", "/api/v1/documents/{document_id}/markdown"),
    ("GET", "/api/v1/documents/{document_id}/html"),
    # Search — resources/search.py
    ("POST", "/api/v1/collections/{collection_id}/search"),
    # Snippets — resources/snippets.py
    ("GET", "/api/v1/collections/{collection_id}/snippets/{kind}"),
    ("POST", "/api/v1/collections/{collection_id}/snippets/{kind}"),
    # Transfers — resources/transfers.py
    ("POST", "/api/v1/collections/{collection_id}/export"),
    ("POST", "/api/v1/collections/import"),
    ("GET", "/api/v1/transfers/{transfer_id}"),
    ("GET", "/api/v1/transfers/{transfer_id}/download"),
    # Pipelines — resources/pipelines.py
    ("GET", "/api/v1/pipelines"),
    ("GET", "/api/v1/pipelines/{key}"),
    ("POST", "/api/v1/pipelines/{key}/inspect"),
    ("POST", "/api/v1/pipelines/{key}/edit"),
    ("POST", "/api/v1/pipelines/{key}/stages/view"),
    ("POST", "/api/v1/pipelines/{key}/stages/apply"),
    # Jobs — resources/jobs.py
    ("GET", "/api/v1/jobs"),
    ("GET", "/api/v1/jobs/{job_id}"),
    ("GET", "/api/v1/jobs/{job_id}/events"),
    ("GET", "/api/v1/jobs/workers/live"),
    ("POST", "/api/v1/jobs/{job_id}/cancel"),
    ("GET", "/api/v1/jobs/cost"),
    ("GET", "/api/v1/jobs/queue"),
    ("GET", "/api/v1/jobs/stage-durations"),
}

# Backend routes with NO SDK method, each with the reason it is deliberately not wrapped.
EXEMPT_ROUTES: dict[tuple[str, str], str] = {
    (
        "GET",
        "/api/v1/jobs/{job_id}/stream",
    ): "SSE stream (text/event-stream) — a long-lived push feed, "
    "not a request/response call; pollers use jobs.get()/get_events() instead.",
}

__all__ = ["ROUTES", "EXEMPT_ROUTES"]
