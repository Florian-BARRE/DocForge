# ====== Code Summary ======
# Server assembly: build the MCPServer instance (registering every tool over the SDK) and, for the
# HTTP transport, build its streamable-HTTP ASGI app (stateless, JSON responses, DNS-rebinding
# protection explicitly disabled) wrapped by the bearer-passthrough middleware.

from __future__ import annotations

# ====== Standard Library Imports ======
import math
from typing import TYPE_CHECKING

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from mcp.server import CacheHint
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette

# ====== Local Project Imports ======
from ._version import __version__
from .auth import BearerPassthroughMiddleware
from .error_translation import ErrorTranslatingMCPServer
from .path_guard import PathGuard
from .tools import DEFAULT_MAX_INLINE_UPLOAD_BYTES, register_all

if TYPE_CHECKING:
    # Only needed for the type annotation (its dynamically-populated env attributes are typed there).
    from config_loader import McpConfig

# base64 inflates a payload by 4/3 (3 raw bytes -> 4 encoded chars, plus padding); the mcp SDK's
# StreamableHTTPSessionManager rejects the whole HTTP request with a 413 BEFORE it ever reaches a
# tool once the raw JSON-RPC body exceeds Settings.max_request_body_size (default 4 MiB — see
# mcp.server.transport_security.DEFAULT_MAX_REQUEST_BODY_SIZE). Left at that default,
# upload_document_bytes/import_collection_bytes's own MCP_MAX_INLINE_UPLOAD_BYTES ceiling (100 MiB
# by default) is unreachable: any base64 payload over ~3 MiB of raw bytes 413s at the transport
# before decode_base64_arg's own, more actionable, ToolError ever runs.
_BASE64_EXPANSION_FACTOR = 4 / 3
# Flat margin absorbing the surrounding JSON-RPC envelope (tool name, other arguments like
# filename/collection_id/metadata, structural quoting/braces) on top of the base64 string itself.
_REQUEST_ENVELOPE_MARGIN_BYTES = 1 * 1024 * 1024

# Freshness hint on tools/list (SEP-2549, sent to 2026-07-28 clients only). The catalogue is static
# per release and the same for every caller (no tool is hidden per API key: the REST API enforces
# a key's scope at call time), hence "public". With no listChanged notification to evict a cached
# list, the TTL is the staleness bound after a redeploy: one hour lets a client skip re-listing
# the 85 schemas for a working session while a new release shows up within the hour (mcp's client
# caps any TTL at 24 h anyway).
_TOOLS_LIST_CACHE_HINT = CacheHint(ttl_ms=60 * 60 * 1000, scope="public")

# Instructions surfaced to the connected LLM so it knows what DocForge is and how to start.
_INSTRUCTIONS = (
    "DocForge is a document intelligence platform. Use these tools to manage collections of "
    "documents, upload files, inspect their parsed pages/chunks/IR, and run hybrid semantic + "
    "keyword search over indexed content. Start with list_collections to learn what is "
    "available; only documents with status 'done' are searchable. Every `collection_id` argument "
    "also accepts a collection ALIAS name (see list_collection_aliases) — a stable name that keeps "
    "working when the collection behind it is rebuilt and switched.\n\n"
    "Typical end-to-end flow: call get_collection_contract_schema() first to learn the exact "
    "field_type/origin/scope enums and supported format tokens, then create_collection(...) — "
    "pass preset='light' for a fast, config-free pipeline to get started quickly. Upload a "
    "document with upload_document (server-local file path) or, when connected remotely over "
    "streamable-HTTP and you hold the file's bytes yourself, upload_document_bytes "
    "(base64-encoded content, no filesystem access needed). Every upload/reingest returns a "
    "job_id — call wait_for_job(job_id) to block until ingestion finishes (or times out) "
    "instead of polling get_job yourself. Once a document's status is 'done', use "
    "search_collection to query it."
)


def build_mcp(
    sdk: AsyncClient,
    path_guard: PathGuard | None = None,
    max_inline_upload_bytes: int = DEFAULT_MAX_INLINE_UPLOAD_BYTES,
) -> MCPServer:
    """
    Build the MCPServer server with every DocForge tool registered.

    Args:
        sdk (AsyncClient): The DocForge API client injected into every tool.
        path_guard (PathGuard | None): Confines `file_path` tool arguments (upload_document,
            import_collection). entrypoint.py always passes one built from McpConfig, wired to the
            selected transport. Left unset here (e.g. by a test building a bare server), the guard
            defaults to the FAIL-CLOSED, HTTP-confined stance with no inbox configured — every
            path-based tool call is refused rather than silently allowed.
        max_inline_upload_bytes (int): Decoded-size ceiling for `upload_document_bytes` /
            `import_collection_bytes`'s `content_base64` argument (operator-configured via
            `MCP_MAX_INLINE_UPLOAD_BYTES`). entrypoint.py always passes McpConfig's value; left
            unset here it falls back to the same 100 MiB default as the config's own default.

    Returns:
        MCPServer: The configured MCP server (transport-agnostic).
    """
    # 1. Fail closed if no guard was supplied — never default to an unrestricted local file read.
    guard = path_guard if path_guard is not None else PathGuard(confine=True, inbox_dir=None)

    # 2. ErrorTranslatingMCPServer wraps every registered tool so a failed SDK call surfaces the
    #    API's own error detail (not just an opaque status code) to the connected LLM. `version`
    #    is docforge's lockstep release (an unversioned 2.x server reports ""). No subscription
    #    bus: there are no resources and the tool list is static, so there is nothing to notify,
    #    and a per-process bus would not fit a stateless, horizontally-scaled server. The
    #    tools/list cache hint lets 2026-07-28 clients reuse the catalogue (_TOOLS_LIST_CACHE_HINT).
    mcp = ErrorTranslatingMCPServer(
        name="DocForge",
        instructions=_INSTRUCTIONS,
        version=__version__,
        subscriptions=False,
        cache_hints={"tools/list": _TOOLS_LIST_CACHE_HINT},
    )
    register_all(mcp, sdk, guard, max_inline_upload_bytes)
    return mcp


def build_http_app(mcp: MCPServer, config: type[McpConfig]) -> Starlette:
    """
    Produce the streamable-HTTP ASGI app, wrapped by the bearer-passthrough middleware.

    The transport settings are ``streamable_http_app()`` kwargs (mcp 2.x no longer reads them off
    ``mcp.settings``). ``stateless_http`` + ``json_response`` keep the service simple and
    proxy-friendly.
    BearerPassthroughMiddleware requires a bearer to be present (401 otherwise, before any tool
    runs) and captures it; VALIDATING that token is delegated to DocForge — this app forwards it
    upstream as-is and never checks the token's validity or scope itself.

    Args:
        mcp (MCPServer): The built MCP server.
        config (type): The McpConfig class (host, path, inline-upload ceiling).

    Returns:
        Starlette: The ASGI application to serve with uvicorn.
    """
    # 1. Raise the transport's raw-HTTP-body ceiling (mcp SDK default: 4 MiB) so it never 413s a
    #    base64 payload that upload_document_bytes/import_collection_bytes would otherwise accept —
    #    derived from MCP_MAX_INLINE_UPLOAD_BYTES rather than its own env var, so the two limits
    #    can never drift apart.
    max_request_body_size = (
        math.ceil(config.MCP_MAX_INLINE_UPLOAD_BYTES * _BASE64_EXPANSION_FACTOR)
        + _REQUEST_ENVELOPE_MARGIN_BYTES
    )

    # 2. Materialise the streamable-HTTP Starlette app with DNS-rebinding protection explicitly
    #    OFF: the SDK auto-enables it (Host restricted to 127.0.0.1/localhost/::1) whenever
    #    transport_security is left unset and `host` is a localhost address — its own default — so
    #    without this explicit setting every remote Host header would be rejected. DNS rebinding
    #    is a browser-CSRF-style threat; this server's clients are programmatic, key-authed MCP
    #    clients (not browsers), so the Host/Origin check adds no value here.
    app = mcp.streamable_http_app(
        streamable_http_path=config.MCP_HTTP_PATH,
        stateless_http=True,
        json_response=True,
        max_request_body_size=max_request_body_size,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        host=config.MCP_HOST,
    )
    # 3. Capture the caller's bearer per request: raw ASGI, outermost, so a request without one is
    #    a 401 before the MCP app runs.
    app.add_middleware(BearerPassthroughMiddleware)
    return app


__all__ = ["build_mcp", "build_http_app"]
