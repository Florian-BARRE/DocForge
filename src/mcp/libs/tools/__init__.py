# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from mcp.server.fastmcp import FastMCP

# ====== Local Project Imports ======
from ..path_guard import PathGuard
from . import (
    audit,
    auth,
    blobs,
    collections,
    corpus,
    documents,
    explorer,
    health,
    jobs,
    pipelines,
    search,
    transfers,
)

# Every domain tool module, in catalogue order. Each exposes register(mcp, sdk).
_MODULES = (
    health,
    auth,
    collections,
    corpus,
    documents,
    explorer,
    search,
    jobs,
    blobs,
    pipelines,
    transfers,
    audit,
)

# The only modules whose tools take a `file_path` argument — these alone need the PathGuard (see
# path_guard.py) to confine reads on the streamable-HTTP transport.
_PATH_GUARDED_MODULES = (documents, transfers)


def register_all(mcp: FastMCP, sdk: AsyncClient, path_guard: PathGuard) -> None:
    """
    Register every DocForge tool on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (AsyncClient): The DocForge API client injected into every tool.
        path_guard (PathGuard): Confines `file_path` tool arguments — passed only to the modules
            that take one (documents, transfers); every other module's signature is unchanged.
    """
    # 1. Delegate to each domain module's register(mcp, sdk[, path_guard])
    for module in _MODULES:
        if module in _PATH_GUARDED_MODULES:
            module.register(mcp, sdk, path_guard)
        else:
            module.register(mcp, sdk)


__all__ = ["register_all"]
