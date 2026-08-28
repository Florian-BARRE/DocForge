# ====== Code Summary ======
# Per-request bearer-token context. The HTTP pass-through middleware (BearerPassthroughMiddleware,
# in auth.py) stashes each incoming request's DocForge API token here so the scoped SDK client
# selection (ScopedSdk, in scoped_sdk.py) can read it without threading the value through every
# tool signature. Untouched by stdio transport, where it always reads as None.

from __future__ import annotations

# ====== Standard Library Imports ======
from contextvars import ContextVar

# Holds the raw bearer token extracted from the current HTTP request's Authorization header.
# None outside of an HTTP request (stdio transport) or when the header is absent/malformed — in
# both cases the caller falls back to the env-configured DOCFORGE_API_TOKEN.
incoming_docforge_token: ContextVar[str | None] = ContextVar(
    "incoming_docforge_token", default=None
)

__all__ = ["incoming_docforge_token"]
