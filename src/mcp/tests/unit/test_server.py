# ====== Code Summary ======
# Unit tests for libs/server.py: the server reports docforge's version and serves no subscriptions,
# the streamable-HTTP app is built stateless + JSON with DNS-rebinding protection explicitly
# disabled and a raised body ceiling, the bearer middleware is its outermost layer, the HTTP app
# no longer requires any MCP-level auth token to build/serve, and (functional sanity) a request carrying a bearer reaches the SDK client selection with that token
# while a bearer-less request is rejected with 401 before ever reaching it.

from __future__ import annotations

# ====== Standard Library Imports ======
import math
from typing import Any

# ====== Third-Party Library Imports ======
import pytest
from docforge_sdk import AsyncClient
from mcp import Client
from mcp.server.mcpserver import MCPServer
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

# ====== Internal Project Imports ======
import libs.scoped_sdk as scoped_sdk_module
from libs._version import __version__
from libs.auth import BearerPassthroughMiddleware
from libs.scoped_sdk import ScopedSdk, ScopedSdkProvider
from libs.server import build_http_app, build_mcp
from libs.token_context import incoming_docforge_token


class _StubMcpConfig:
    """Minimal stand-in for McpConfig — only the attributes build_http_app reads."""

    MCP_HOST = "127.0.0.1"
    MCP_PORT = 9000
    MCP_HTTP_PATH = "/mcp"
    MCP_MAX_INLINE_UPLOAD_BYTES = 100 * 1024 * 1024


def _streamable_http_app_kwargs(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Build the HTTP app while recording the kwargs build_http_app passes to the SDK."""
    seen: dict[str, Any] = {}
    original = MCPServer.streamable_http_app

    def spy(self: MCPServer, **kwargs: Any) -> Starlette:
        seen.update(kwargs)
        return original(self, **kwargs)

    monkeypatch.setattr(MCPServer, "streamable_http_app", spy)
    build_http_app(build_mcp(AsyncClient("http://localhost:8000")), _StubMcpConfig)  # type: ignore[arg-type]
    return seen


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_build_mcp_reports_the_docforge_version_and_serves_no_subscriptions(
    mode: str,
) -> None:
    """serverInfo.version is docforge's (2.x reports "" otherwise); no listChanged/subscribe."""
    async with Client(build_mcp(AsyncClient("http://localhost:8000")), mode=mode) as client:
        info = client.server_info
        capabilities = client.server_capabilities
    assert info is not None
    assert (info.name, info.version) == ("DocForge", __version__)
    assert capabilities.tools is not None and not capabilities.tools.list_changed
    assert capabilities.resources is None or not capabilities.resources.subscribe


def test_http_app_is_stateless_json_and_disables_dns_rebinding_protection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    The transport settings go to the SDK as kwargs; DNS-rebinding protection must be passed
    explicitly OFF, since the SDK auto-enables it for a localhost `host` when left unset.
    """
    kwargs = _streamable_http_app_kwargs(monkeypatch)
    assert kwargs["streamable_http_path"] == _StubMcpConfig.MCP_HTTP_PATH
    assert kwargs["stateless_http"] is True
    assert kwargs["json_response"] is True
    security = kwargs["transport_security"]
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
    # user_middleware[0] is the outermost layer: no bearer -> 401 before the MCP app runs.
    assert app.user_middleware[0].cls is BearerPassthroughMiddleware


def test_http_app_raises_the_transport_body_ceiling_above_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    build_http_app must raise mcp SDK's max_request_body_size (default 4 MiB — see
    mcp.server.transport_security.DEFAULT_MAX_REQUEST_BODY_SIZE) well above it, so a base64
    payload sized for MCP_MAX_INLINE_UPLOAD_BYTES never 413s at the transport before
    upload_document_bytes/import_collection_bytes's own decode_base64_arg cap ever runs.
    """
    from mcp.server.transport_security import DEFAULT_MAX_REQUEST_BODY_SIZE

    ceiling = _streamable_http_app_kwargs(monkeypatch)["max_request_body_size"]

    # base64 inflates the raw inline-upload cap by 4/3; the ceiling must clear that comfortably.
    assert ceiling > DEFAULT_MAX_REQUEST_BODY_SIZE
    assert ceiling >= math.ceil(_StubMcpConfig.MCP_MAX_INLINE_UPLOAD_BYTES * 4 / 3)


class _FakeAsyncClient:
    """Stand-in for docforge_sdk.AsyncClient that records the token it was built with."""

    def __init__(self, base_url: str, timeout: float, api_token: str = "") -> None:
        self.api_token = api_token


def test_caller_bearer_reaches_the_scoped_sdk_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Functional sanity, wired the way entrypoint.py wires HTTP mode (require_bearer=True): a
    request's own bearer, captured by the middleware, selects the matching SDK client, while a
    bearer-less request is rejected with 401 before the tool-equivalent handler ever runs — proving
    end to end that an anonymous HTTP request can never resolve the fallback token's client.
    """
    monkeypatch.setattr(scoped_sdk_module, "AsyncClient", _FakeAsyncClient)
    provider = ScopedSdkProvider(
        "http://api", timeout=5.0, fallback_token="fallback-tok", require_bearer=True
    )
    sdk = ScopedSdk(provider)
    calls: list[str] = []

    async def whoami(request: Request) -> JSONResponse:
        # Mirrors what a tool does: read an attribute off the injected sdk at call time.
        calls.append("handler-called")
        return JSONResponse({"api_token": sdk.api_token})

    app = Starlette(routes=[Route("/whoami", whoami)])
    app.add_middleware(BearerPassthroughMiddleware)
    client = TestClient(app)

    anonymous = client.get("/whoami")
    assert anonymous.status_code == 401
    assert calls == [], "no bearer -> the handler must never run, so it can't hit the fallback"

    assert client.get("/whoami", headers={"Authorization": "Bearer caller-key"}).json() == {
        "api_token": "caller-key"
    }
    # Outside of any request, the contextvar is unset again.
    assert incoming_docforge_token.get() is None
