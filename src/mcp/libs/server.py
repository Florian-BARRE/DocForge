# ====== Code Summary ======
# Server assembly: build the FastMCP instance (registering every tool over the SDK, with
# DNS-rebinding protection explicitly disabled) and, for the HTTP transport, wrap its
# streamable-HTTP ASGI app with the bearer-passthrough middleware.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import TYPE_CHECKING

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette

# ====== Local Project Imports ======
from .auth import BearerPassthroughMiddleware
from .tools import register_all

if TYPE_CHECKING:
    # Only needed for the type annotation (its dynamically-populated env attributes are typed there).
    from config_loader import McpConfig

# Instructions surfaced to the connected LLM so it knows what DocForge is and how to start.
_INSTRUCTIONS = (
    "DocForge is a document intelligence platform. Use these tools to manage collections of "
    "documents, upload files, inspect their parsed pages/chunks/IR, and run hybrid semantic + "
    "keyword search over indexed content. Start with list_collections to learn what is "
    "available; only documents with status 'done' are searchable."
)


def build_mcp(sdk: AsyncClient) -> FastMCP:
    """
    Build the FastMCP server with every DocForge tool registered.

    Args:
        sdk (AsyncClient): The DocForge API client injected into every tool.

    Returns:
        FastMCP: The configured MCP server (transport-agnostic).
    """
    # 1. Create the server with DNS-rebinding protection explicitly OFF. FastMCP auto-enables it
    #    (host restricted to 127.0.0.1/localhost/::1) whenever transport_security is left unset AND
    #    the default host "127.0.0.1" is in effect AT CONSTRUCTION TIME — but build_http_app() only
    #    overrides mcp.settings.host to "0.0.0.0" AFTER this call, so without this explicit override
    #    the protection would silently stay localhost-only and reject every remote Host header. DNS
    #    rebinding is a browser-CSRF-style threat; this server's clients are programmatic, key-authed
    #    MCP clients (not browsers), so the Host/Origin check adds no value here.
    mcp = FastMCP(
        name="DocForge",
        instructions=_INSTRUCTIONS,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    register_all(mcp, sdk)
    return mcp


def build_http_app(mcp: FastMCP, config: type[McpConfig]) -> Starlette:
    """
    Produce the streamable-HTTP ASGI app, wrapped by the bearer-passthrough middleware.

    Settings are applied BEFORE ``streamable_http_app()`` so the session manager is built in the
    intended mode. ``stateless_http`` + ``json_response`` keep the service simple and proxy-friendly.
    Auth is delegated to DocForge: each request's own Authorization bearer is captured by
    BearerPassthroughMiddleware and forwarded upstream — this app never checks it itself.

    Args:
        mcp (FastMCP): The built MCP server.
        config (type): The McpConfig class (host/port/path).

    Returns:
        Starlette: The ASGI application to serve with uvicorn.
    """
    # 1. Configure transport settings before the app is materialised
    mcp.settings.host = config.MCP_HOST
    mcp.settings.port = config.MCP_PORT
    mcp.settings.streamable_http_path = config.MCP_HTTP_PATH
    mcp.settings.stateless_http = True
    mcp.settings.json_response = True

    # 2. Materialise the streamable-HTTP Starlette app and capture the caller's bearer per request
    app = mcp.streamable_http_app()
    app.add_middleware(BearerPassthroughMiddleware)
    return app


__all__ = ["build_mcp", "build_http_app"]
