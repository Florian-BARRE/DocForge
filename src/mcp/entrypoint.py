# ====== Code Summary ======
# Entry point for the standalone DocForge MCP server (name aligned with docforge/entrypoint.py).
# Wires McpConfig → AsyncClient (docforge_sdk) → FastMCP, then runs the requested transport:
#   - stdio           → local Claude Desktop / Claude Code
#   - streamable-http → long-lived container service, behind the bearer-auth middleware
# Invoked as `python entrypoint.py` (it cannot be a pure `uvicorn entrypoint:app` target because
# the stdio mode is not an ASGI server).

# ====== Standard Library Imports ======
import asyncio

# ====== Third-Party Library Imports ======
import uvicorn
from docforge_sdk import AsyncClient
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from config_loader import McpConfig  # MUST be first — registers sys.path + configures logging
from libs.server import build_http_app, build_mcp

logger = loggerplusplus.bind(identifier="McpServer")


def main() -> None:
    """
    Build the MCP server and run it under the configured transport.

    Raises:
        RuntimeError: When HTTP transport is selected without an MCP_AUTH_TOKEN.
    """
    # 1. Build the SDK client and the MCP server (tools registered over the SDK).
    #    Pass DOCFORGE_API_TOKEN so every outbound request carries "Authorization: Bearer <token>"
    #    when the DocForge API has AUTH_ENABLED=true. An empty token is forward-compatible with
    #    auth-disabled deployments (no Authorization header will be sent in that case).
    sdk = AsyncClient(
        McpConfig.DOCFORGE_API_URL,
        timeout=float(McpConfig.MCP_API_TIMEOUT_S),
        api_token=McpConfig.DOCFORGE_API_TOKEN,
    )
    mcp = build_mcp(sdk)

    # 2. stdio transport — local protocol over stdin/stdout (no auth, no network)
    if McpConfig.MCP_TRANSPORT == "stdio":
        logger.info(f"Starting DocForge MCP server (stdio) -> {McpConfig.DOCFORGE_API_URL}")
        try:
            mcp.run(transport="stdio")
        finally:
            asyncio.run(sdk.aclose())
        return

    # 3. HTTP transport — refuse to expose the corpus without a bearer token
    if not McpConfig.MCP_AUTH_TOKEN:
        raise RuntimeError(
            "MCP_AUTH_TOKEN is required when MCP_TRANSPORT is not 'stdio' — refusing to expose "
            "the DocForge MCP server without authentication."
        )

    # 4. Serve the auth-wrapped streamable-HTTP app
    app = build_http_app(mcp, McpConfig)
    logger.info(
        f"Starting DocForge MCP server (streamable-http) on "
        f"{McpConfig.MCP_HOST}:{McpConfig.MCP_PORT}{McpConfig.MCP_HTTP_PATH} "
        f"-> {McpConfig.DOCFORGE_API_URL}"
    )
    try:
        uvicorn.run(app, host=McpConfig.MCP_HOST, port=McpConfig.MCP_PORT)
    finally:
        asyncio.run(sdk.aclose())


if __name__ == "__main__":
    main()
