# ====== Code Summary ======
# Defines McpConfig (env-based settings) and configures the loggerplusplus sinks for the
# standalone DocForge MCP server. This file is imported FIRST in entrypoint.py so that the
# class body registers the app root on sys.path before any `libs.*` import is resolved.
#
# This app is a self-contained HTTP client of the DocForge REST API — it deliberately does NOT
# import the docforge RUNTIME_CONFIG (which would require Postgres/S3 secrets it never uses).

# ====== Standard Library Imports ======
import pathlib
import sys

# ====== Third-Party Library Imports ======
from configplusplus import EnvConfigLoader, env
from loggerplusplus import formats as lpp_formats
from loggerplusplus import loggerplusplus

# ─── Reset logger before anything else ───
loggerplusplus.remove()


class McpConfig(EnvConfigLoader):
    """
    Environment-driven configuration for the standalone DocForge MCP server.

    All values are read from environment variables at class-evaluation time. Secrets (any name
    containing TOKEN/SECRET/…) are auto-masked in ``__str__`` output. The MCP server only needs
    the API URL plus its own transport/auth knobs — no database or object-store credentials.
    """

    # ───── Paths & dirs ─────
    # Root of the mcp application (this file's directory).
    PATH_ROOT_DIR: pathlib.Path = pathlib.Path(__file__).resolve().parent

    # Register the app root on sys.path so `from libs.tools... import ...` resolves regardless of
    # how the entry point is invoked (python entrypoint.py, pytest, or uvicorn-as-module).
    sys.path.append(str(PATH_ROOT_DIR))

    # ───── Logging (mandatory 5 — drive the logging setup) ─────
    LOGGING_CONSOLE_LEVEL: str = env("LOGGING_CONSOLE_LEVEL", default="INFO")
    LOGGING_FILE_LEVEL: str = env("LOGGING_FILE_LEVEL", default="DEBUG")
    LOGGING_ENABLE_CONSOLE: bool = env("LOGGING_ENABLE_CONSOLE", cast=bool, default="true")
    LOGGING_ENABLE_FILE: bool = env("LOGGING_ENABLE_FILE", cast=bool, default="false")
    LOGGING_LPP_FORMAT: str = env("LOGGING_LPP_FORMAT", default="ShortFormat")

    # ───── DocForge API target ─────
    # Base URL of the DocForge REST API. Inside docker compose this is the service name
    # (http://docforge:8000); for a local stdio run it is typically http://localhost:8000.
    DOCFORGE_API_URL: str = env("DOCFORGE_API_URL", default="http://localhost:8000")
    # Per-request timeout (seconds) for SDK HTTP calls.
    MCP_API_TIMEOUT_S: int = env("MCP_API_TIMEOUT_S", cast=int, default="60")
    # Bearer token sent on every outbound request to the DocForge REST API when AUTH_ENABLED=true
    # on the docforge side. Must match the DocForge AUTH_ROOT_API_KEY or any per-user API key
    # registered in the DB. Leave empty only when targeting a DocForge instance with auth disabled.
    # The name contains "TOKEN" so configplusplus auto-masks this value in log output.
    DOCFORGE_API_TOKEN: str = env("DOCFORGE_API_TOKEN", required=False, default="")

    # ───── MCP transport ─────
    # "stdio"        → local Claude Desktop / Claude Code (protocol over stdin/stdout).
    # "streamable-http" → long-lived container service (HTTP, behind the bearer middleware).
    MCP_TRANSPORT: str = env("MCP_TRANSPORT", default="stdio")
    # Bind address — must be 0.0.0.0 inside a container to be reachable from the host.
    MCP_HOST: str = env("MCP_HOST", default="0.0.0.0")
    # Internal listen port (mapped to a host port by docker compose).
    MCP_PORT: int = env("MCP_PORT", cast=int, default="9000")
    # URL path the streamable-http endpoint is served on.
    MCP_HTTP_PATH: str = env("MCP_HTTP_PATH", default="/mcp")
    # Shared bearer token required on every HTTP request. Empty is only valid in stdio mode;
    # the entry point refuses to start an HTTP server without it. Auto-masked when printed.
    MCP_AUTH_TOKEN: str = env("MCP_AUTH_TOKEN", required=False, default="")


# ─── Apply logging configuration AFTER class definition ───
# In stdio mode, stdout is the MCP protocol channel — logs MUST go to stderr to avoid
# corrupting the JSON-RPC stream. In HTTP mode, stdout is free for logs.
_console_sink = sys.stderr if McpConfig.MCP_TRANSPORT == "stdio" else sys.stdout
_lpp_format_cls = getattr(lpp_formats, McpConfig.LOGGING_LPP_FORMAT, lpp_formats.ShortFormat)
_lpp_format = _lpp_format_cls()

if McpConfig.LOGGING_ENABLE_CONSOLE:
    loggerplusplus.add(
        sink=_console_sink,
        level=McpConfig.LOGGING_CONSOLE_LEVEL,
        format=_lpp_format,
    )

if McpConfig.LOGGING_ENABLE_FILE:
    loggerplusplus.add(
        pathlib.Path("logs"),
        level=McpConfig.LOGGING_FILE_LEVEL,
        format=_lpp_format,
        rotation="1 week",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=False,
    )
