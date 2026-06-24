# MCP Agent — Memory Index

Component: **`src/mcp/`** — standalone MCP server, a PURE HTTP client of the DocForge REST API.
Deploy: compose service `mcp`, image `docforge-mcp:latest`, in-container root `/app/mcp`, env folder
`services/mcp/`, talks to `http://docforge:8000`. Bi-transport (stdio | streamable-http), 51 tools,
self-contained `McpConfig` (NOT `RUNTIME_CONFIG`). Two-layer split: `libs/sdk/` (typed HTTP client) +
`libs/tools/` (1-line `@mcp.tool` wrappers).

- [mcp-pure-http-client](mcp-pure-http-client.md) — the pure-HTTP-client invariant (never import `common_libs.*`) + which python.md deviations are intentional here
- [backend-endpoint-map](backend-endpoint-map.md) — REST path/verb/body facts the SDK must match, derived from `app/backend/app.py` + routers
