# ====== Code Summary ======
# Unit tests for libs/server.py: DNS-rebinding protection is explicitly disabled on the built
# FastMCP instance, the HTTP app no longer requires any MCP-level auth token to build/serve, and
# (functional sanity) a request carrying a bearer reaches the SDK client selection with that token.

from __future__ import annotations

# ====== Third-Party Library Imports ======
import pytest
from docforge_sdk import AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

# ====== Internal Project Imports ======
import libs.scoped_sdk as scoped_sdk_module
from libs.auth import BearerPassthroughMiddleware
from libs.scoped_sdk import ScopedSdk, ScopedSdkProvider
from libs.server import build_http_app, build_mcp
from libs.token_context import incoming_docforge_token


class _StubMcpConfig:
    """Minimal stand-in for McpConfig — only the attributes build_http_app reads."""

    MCP_HOST = "127.0.0.1"
    MCP_PORT = 9000
    MCP_HTTP_PATH = "/mcp"


def test_build_mcp_disables_dns_rebinding_protection() -> None:
    """FastMCP must be built with DNS-rebinding protection OFF regardless of host."""
    mcp = build_mcp(AsyncClient("http://localhost:8000"))
    security = mcp.settings.transport_security
    assert security is not None
    assert security.enable_dns_rebinding_protection is False


def test_build_http_app_does_not_require_any_mcp_level_token() -> None:
    """build_http_app builds successfully from a config with no auth-token attribute at all."""
    assert not hasattr(_StubMcpConfig, "MCP_AUTH_TOKEN")
    mcp = build_mcp(AsyncClient("http://localhost:8000"))
    app = build_http_app(mcp, _StubMcpConfig)  # type: ignore[arg-type]
    assert isinstance(app, Starlette)


def test_http_app_is_wrapped_by_the_bearer_passthrough_middleware() -> None:
    """The streamable-HTTP app carries BearerPassthroughMiddleware, not a static-token gate."""
    mcp = build_mcp(AsyncClient("http://localhost:8000"))
    app = build_http_app(mcp, _StubMcpConfig)  # type: ignore[arg-type]
    middleware_classes = {entry.cls for entry in app.user_middleware}
    assert BearerPassthroughMiddleware in middleware_classes


class _FakeAsyncClient:
    """Stand-in for docforge_sdk.AsyncClient that records the token it was built with."""

    def __init__(self, base_url: str, timeout: float, api_token: str = "") -> None:
        self.api_token = api_token


def test_caller_bearer_reaches_the_scoped_sdk_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Functional sanity: a request's own bearer, captured by the middleware, selects the matching
    SDK client — proving the passthrough mechanism end to end without a real DocForge instance.
    """
    monkeypatch.setattr(scoped_sdk_module, "AsyncClient", _FakeAsyncClient)
    provider = ScopedSdkProvider("http://api", timeout=5.0, fallback_token="fallback-tok")
    sdk = ScopedSdk(provider)

    async def whoami(request: Request) -> JSONResponse:
        # Mirrors what a tool does: read an attribute off the injected sdk at call time.
        return JSONResponse({"api_token": sdk.api_token})

    app = Starlette(routes=[Route("/whoami", whoami)])
    app.add_middleware(BearerPassthroughMiddleware)
    client = TestClient(app)

    assert client.get("/whoami").json() == {"api_token": "fallback-tok"}
    assert client.get("/whoami", headers={"Authorization": "Bearer caller-key"}).json() == {
        "api_token": "caller-key"
    }
    # Outside of any request, the contextvar is unset again.
    assert incoming_docforge_token.get() is None
