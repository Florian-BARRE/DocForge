---
name: mcp-pure-http-client
description: Verifying the MCP app (src/mcp/) stays a pure HTTP client + which python.md deviations are intentional there
metadata:
  type: pattern
---

`src/mcp/` is a standalone MCP server that MUST be a pure HTTP client of the DocForge REST
API — it must never import the docforge domain libs (`common_libs.domain/pipeline/storage/providers/
search/config/observability`). This keeps it out of the layer DAG and lets it deploy as a ~150 MB image.

**How to verify the invariant (fast):** grep `src/mcp/` for `from common_libs`, `import docforge`,
and `from config import RUNTIME_CONFIG`. Any hit is a BLOCKER. Note: inside `src/mcp/`,
`from libs.sdk ...` / `from libs.tools ...` / `from libs.auth ...` / `from libs.server ...` are the
app's OWN `libs/` (under `src/mcp/libs/`) — not a leak.

**Sanctioned deviations from python.md (do NOT flag these in this app):**
- `config_loader.py` flat file instead of a `config/` package — python.md explicitly allows this for a
  single runtime config with no YAML. It defines `McpConfig(EnvConfigLoader)`, NOT `RUNTIME_CONFIG`, on
  purpose (a pure HTTP client must not be forced to carry Postgres/S3 secrets).
- The class is named `McpConfig`, not `RUNTIME_CONFIG`. Intentional and consistent across the app.
- Entry point is `python entrypoint.py` dispatching on `MCP_TRANSPORT` (stdio | streamable-http), not a
  `uvicorn entrypoint:app` target — stdio mode is not an ASGI server, so the standard FastAPI entry rule
  doesn't apply.
- Console sink goes to STDERR in stdio mode (stdout is the JSON-RPC protocol channel). Correct, not a bug.
- `libs/__init__.py` and `libs/tools/__init__.py` are thin; `tools/__init__.py` legitimately lacks the
  shape of a domain package but does end with `__all__ = ["register_all"]`. `libs/__init__.py` is a bare
  package marker (comment only) — acceptable for a namespace-only package.

**Things that ARE worth flagging if they regress:**
- `DocForgeClient.aclose()` / `DocForgeTransport.aclose()` exist but are never called from `entrypoint.py`
  — the httpx pool is not closed on shutdown. Nit only (process dies wholesale), but if a graceful
  shutdown path is added later, wire aclose into it.
- Windows cp1252 console: every logger/RuntimeError string must stay ASCII (use `->`, never the arrow
  char). Non-ASCII is fine in comments/docstrings/.env (never hits the console). As of P8 review all
  runtime-emitted strings were ASCII-clean.

**Outbound DocForge API auth (MCP -> DocForge):**
- `McpConfig.DOCFORGE_API_TOKEN` (str, optional, default `""`) — set when `AUTH_ENABLED=true` on the
  DocForge side. Must match `AUTH_ROOT_API_KEY` or a per-user DB API key.
- `DocForgeTransport.__init__` accepts `api_token: str = ""`. When non-empty, it is set as a default
  header `Authorization: Bearer <token>` on the `httpx.AsyncClient` at construction time, so **all**
  verbs (get/post/put/delete/upload/get_bytes) inherit it without any per-call code.
- When empty, no `Authorization` header is attached — backward-compatible with auth-disabled deployments.
- `DocForgeClient.__init__` accepts `api_token: str = ""` and forwards it to `DocForgeTransport`.
- `entrypoint.py` passes `api_token=McpConfig.DOCFORGE_API_TOKEN` to `DocForgeClient`.
- `services/mcp/.env` and `.env.example`: `#DOCFORGE_API_TOKEN=` (commented, explained).
- Two new unit tests: `test_authorization_header_sent_when_token_set` and
  `test_authorization_header_absent_when_token_empty` in `src/mcp/tests/unit/test_sdk.py`.
- The `_client()` helper in the test file now accepts `api_token` and copies `default_headers` when
  swapping in the mock transport, so the Authorization header survives the swap.
- NOTE: this is OUTBOUND auth (MCP → DocForge). The INBOUND auth (client → MCP) remains unchanged in
  `libs/auth.py` (`StaticBearerAuthMiddleware`, keyed by `MCP_AUTH_TOKEN`). The two are independent.

See [[backend-endpoint-map]] for the REST contract the SDK is validated against.
