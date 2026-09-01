# ====== Code Summary ======
# Unit tests for BearerPassthroughMiddleware: an HTTP request with no (or malformed/empty) bearer
# is rejected with 401 and the wrapped app is NEVER invoked — this is the enforcement point that
# closes the anonymous-request-defaults-to-a-privileged-token hole. A request that DOES carry a
# bearer is let through, with the token stashed into the contextvar for the downstream handler.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

# ====== Internal Project Imports ======
from libs.auth import BearerPassthroughMiddleware
from libs.token_context import incoming_docforge_token


def _build_client(calls: list[str] | None = None) -> TestClient:
    """Build a tiny app behind the passthrough middleware that echoes the captured token."""

    async def echo_token(request: Request) -> JSONResponse:
        if calls is not None:
            calls.append("app-called")
        return JSONResponse({"token": incoming_docforge_token.get()})

    app = Starlette(routes=[Route("/mcp", echo_token)])
    app.add_middleware(BearerPassthroughMiddleware)
    return TestClient(app)


def test_missing_authorization_is_rejected_with_401_and_never_reaches_the_app() -> None:
    """No Authorization header -> 401, and the wrapped app (would-be tool call) never runs."""
    calls: list[str] = []
    res = _build_client(calls).get("/mcp")
    assert res.status_code == 401
    assert calls == [], "the wrapped app must not be invoked for a bearer-less request"


def test_bearer_token_is_captured_into_context() -> None:
    """A bearer token in Authorization is exposed to the downstream handler via the contextvar."""
    res = _build_client().get("/mcp", headers={"Authorization": "Bearer caller-key-123"})
    assert res.status_code == 200
    assert res.json() == {"token": "caller-key-123"}


@pytest.mark.parametrize(
    "headers",
    [
        {"Authorization": "Basic dXNlcjpwYXNz"},
        {"Authorization": "Bearer "},
        {},
    ],
)
def test_non_bearer_or_empty_authorization_is_rejected_with_401(
    headers: dict[str, Any],
) -> None:
    """A non-bearer scheme, an empty bearer, or a missing header are all treated as no token."""
    calls: list[str] = []
    res = _build_client(calls).get("/mcp", headers=headers)
    assert res.status_code == 401
    assert calls == []


def test_context_does_not_leak_across_requests() -> None:
    """The contextvar is scoped per request — a token from one call must not bleed into the next."""
    client = _build_client()
    first = client.get("/mcp", headers={"Authorization": "Bearer first-key"})
    second = client.get("/mcp")

    assert first.json() == {"token": "first-key"}
    assert second.status_code == 401
