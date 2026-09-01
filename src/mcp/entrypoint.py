# ====== Code Summary ======
# Entry point for the standalone DocForge MCP server (name aligned with docforge/entrypoint.py).
# Wires McpConfig → ScopedSdkProvider (docforge_sdk) → FastMCP, then runs the requested transport:
#   - stdio           → local Claude Desktop / Claude Code (env DOCFORGE_API_TOKEN, no network)
#   - streamable-http → long-lived container service; auth is delegated to DocForge — each
#                        request's own Authorization bearer is forwarded upstream as-is, and a
#                        request with no bearer is rejected with 401 (no fallback over HTTP)
# Invoked as `python entrypoint.py` (it cannot be a pure `uvicorn entrypoint:app` target because
# the stdio mode is not an ASGI server).

# ====== Standard Library Imports ======
import asyncio
from typing import cast

# ====== Third-Party Library Imports ======
import uvicorn
from docforge_sdk import AsyncClient
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from config_loader import McpConfig  # MUST be first — registers sys.path + configures logging
from libs.scoped_sdk import ScopedSdk, ScopedSdkProvider
from libs.server import build_http_app, build_mcp

logger = loggerplusplus.bind(identifier="McpServer")


def main() -> None:
    """Build the MCP server and run it under the configured transport."""
    # 1. Build the per-token SDK client provider. DOCFORGE_API_TOKEN is the fallback used ONLY by
    #    stdio (require_bearer=False) — no Authorization header exists to forward there. In HTTP
    #    mode (require_bearer=True) every call must carry its own caller token (see scoped_sdk.py);
    #    BearerPassthroughMiddleware already rejects a bearer-less request with 401 before any tool
    #    runs, so the fallback is never resolved to serve a network request. An HTTP request that
    #    DOES carry a bearer gets its own cached client using THAT token.
    provider = ScopedSdkProvider(
        McpConfig.DOCFORGE_API_URL,
        timeout=float(McpConfig.MCP_API_TIMEOUT_S),
        fallback_token=McpConfig.DOCFORGE_API_TOKEN,
        require_bearer=McpConfig.MCP_TRANSPORT != "stdio",
    )
    # 2. Inject the scoped proxy wherever an AsyncClient is expected — every tool file keeps its
    #    original `sdk: AsyncClient` signature; only this cast site knows it's actually the proxy.
    sdk = cast(AsyncClient, ScopedSdk(provider))
    mcp = build_mcp(sdk)

    # 3. stdio transport — local protocol over stdin/stdout (no network, contextvar never set)
    if McpConfig.MCP_TRANSPORT == "stdio":
        logger.info(f"Starting DocForge MCP server (stdio) -> {McpConfig.DOCFORGE_API_URL}")
        try:
            mcp.run(transport="stdio")
        finally:
            asyncio.run(provider.aclose())
        return

    # 4. Serve the streamable-HTTP app — auth is fully delegated to DocForge (see build_http_app);
    #    the caller's own DocForge API key must be presented on every request. Plain HTTP works;
    #    front with TLS on an untrusted network since the key travels in the Authorization header.
    app = build_http_app(mcp, McpConfig)
    logger.info(
        f"Starting DocForge MCP server (streamable-http) on "
        f"{McpConfig.MCP_HOST}:{McpConfig.MCP_PORT}{McpConfig.MCP_HTTP_PATH} "
        f"-> {McpConfig.DOCFORGE_API_URL} (auth delegated to DocForge)"
    )
    try:
        uvicorn.run(app, host=McpConfig.MCP_HOST, port=McpConfig.MCP_PORT)
    finally:
        asyncio.run(provider.aclose())


if __name__ == "__main__":
    main()
