---
name: mcp-pure-http-client
description: Verifying the docforge_mcp app stays a pure HTTP client + which python.md deviations are intentional there
metadata:
  type: pattern
---

`src/docforge_mcp/` is a standalone MCP server that MUST be a pure HTTP client of the DocForge REST
API — it must never import the docforge domain `libs/` (domain/pipeline/storage/providers/search/
config/observability). This keeps it out of the layer DAG and lets it deploy as a ~150 MB image.

**How to verify the invariant (fast):** grep the whole tree for `from libs.domain`, `from libs.pipeline`,
`from libs.storage`, `from libs.providers`, `from libs.search`, `from libs.config`, `from libs.observability`,
`import docforge`, and `from config import RUNTIME_CONFIG`. Any hit is a BLOCKER. Note: inside docforge_mcp,
`from libs.sdk ...` / `from libs.tools ...` / `from libs.auth ...` are the app's OWN libs/ — not a leak.

**Sanctioned deviations from python.md (do NOT flag these in this app):**
- `config_loader.py` flat file instead of a `config/` package — python.md explicitly allows this for a
  single runtime config with no YAML. It defines `McpConfig(EnvConfigLoader)`, NOT `RUNTIME_CONFIG`, on
  purpose (a pure HTTP client must not be forced to carry Postgres/S3 secrets).
- The class is named `McpConfig`, not `RUNTIME_CONFIG`. Intentional and consistent across the app.
- Entry point is `python entrypoint.py` dispatching on `MCP_TRANSPORT` (stdio | streamable-http), not a
  `uvicorn entrypoint:app` target — stdio mode is not an ASGI server, so the standard FastAPI entry rule
  doesn't apply.
- Console sink goes to STDERR in stdio mode (stdout is the JSON-RPC protocol channel). Correct, not a bug.
- `libs/__init__.py` and `libs/tools/__init__.py` are thin; `tools/__init__.py` legitimately lacks `__all__`
  shape of a domain package but does end with `__all__ = ["register_all"]`. `libs/__init__.py` is a bare
  package marker (comment only) — acceptable for a namespace-only package.

**Things that ARE worth flagging if they regress:**
- `DocForgeClient.aclose()` / `DocForgeTransport.aclose()` exist but are never called from `entrypoint.py`
  — the httpx pool is not closed on shutdown. Nit only (process dies wholesale), but if a graceful
  shutdown path is added later, wire aclose into it.
- Windows cp1252 console: every logger/RuntimeError string must stay ASCII (use `->`, never the arrow
  char). Non-ASCII is fine in comments/docstrings/.env (never hits the console). As of P8 review all
  runtime-emitted strings were ASCII-clean.

See [[backend-endpoint-map]] for the REST contract the SDK is validated against.
