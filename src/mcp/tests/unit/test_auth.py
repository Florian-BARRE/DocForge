# ====== Code Summary ======
# Unit tests for BearerPassthroughMiddleware: it never rejects a request itself — it only stashes
# the incoming Authorization bearer (or None) into the token contextvar for the downstream handler.

from __future__ import annotations

# ====== Third-Party Library Imports ======
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

# ====== Internal Project Imports ======
from libs.auth import BearerPassthroughMiddleware
from libs.token_context import incoming_docforge_token


def _build_client() -> TestClient:
    """Build a tiny app behind the passthrough middleware that echoes the captured token."""

    async def echo_token(request: Request) -> JSONResponse:
        return JSONResponse({"token": incoming_docforge_token.get()})

    app = Starlette(routes=[Route("/mcp", echo_token)])
    app.add_middleware(BearerPassthroughMiddleware)
    return TestClient(app)


def test_missing_authorization_leaves_context_empty_and_still_serves() -> None:
    """No Authorization header -> the request is served (200), contextvar reads None."""
    res = _build_client().get("/mcp")
    assert res.status_code == 200
    assert res.json() == {"token": None}


def test_bearer_token_is_captured_into_context() -> None:
    """A bearer token in Authorization is exposed to the downstream handler via the contextvar."""
    res = _build_client().get("/mcp", headers={"Authorization": "Bearer caller-key-123"})
    assert res.status_code == 200
    assert res.json() == {"token": "caller-key-123"}


def test_non_bearer_scheme_is_ignored() -> None:
    """A non-bearer Authorization scheme (e.g. Basic) does not leak into the contextvar."""
    res = _build_client().get("/mcp", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert res.status_code == 200
    assert res.json() == {"token": None}


def test_context_does_not_leak_across_requests() -> None:
    """The contextvar is scoped per request — a token from one call must not bleed into the next."""
    client = _build_client()
    first = client.get("/mcp", headers={"Authorization": "Bearer first-key"})
    second = client.get("/mcp")

    assert first.json() == {"token": "first-key"}
    assert second.json() == {"token": None}
