# ====== Code Summary ======
# Server assembly: build the FastMCP instance (registering every tool over the SDK) and, for the
# HTTP transport, wrap its streamable-HTTP ASGI app with the static bearer-auth middleware.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import TYPE_CHECKING

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette

# ====== Local Project Imports ======
from .auth import StaticBearerAuthMiddleware
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
    # 1. Create the server and register the full tool catalogue
    mcp = FastMCP(name="DocForge", instructions=_INSTRUCTIONS)
    register_all(mcp, sdk)
    return mcp


def build_http_app(mcp: FastMCP, config: type[McpConfig]) -> Starlette:
    """
    Produce the streamable-HTTP ASGI app, gated by the static bearer-auth middleware.

    Settings are applied BEFORE ``streamable_http_app()`` so the session manager is built in the
    intended mode. ``stateless_http`` + ``json_response`` keep the service simple and proxy-friendly.

    Args:
        mcp (FastMCP): The built MCP server.
        config (type): The McpConfig class (host/port/path/token).

    Returns:
        Starlette: The auth-wrapped ASGI application to serve with uvicorn.
    """
    # 1. Configure transport settings before the app is materialised
    mcp.settings.host = config.MCP_HOST
    mcp.settings.port = config.MCP_PORT
    mcp.settings.streamable_http_path = config.MCP_HTTP_PATH
    mcp.settings.stateless_http = True
    mcp.settings.json_response = True

    # 2. Materialise the streamable-HTTP Starlette app and gate it behind the bearer middleware
    app = mcp.streamable_http_app()
    app.add_middleware(StaticBearerAuthMiddleware, expected_token=config.MCP_AUTH_TOKEN)
    return app


__all__ = ["build_mcp", "build_http_app"]
