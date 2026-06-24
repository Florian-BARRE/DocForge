# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from mcp.server.fastmcp import FastMCP

# ====== Local Project Imports ======
from ..sdk import DocForgeClient
from . import (
    access,
    auth,
    chunks,
    collection_config,
    collections,
    discovery,
    documents,
    files,
    health,
    jobs,
    limits,
    monitoring,
    pages,
    search,
    users,
)

# Every domain tool module, in catalogue order. Each exposes register(mcp, sdk).
_MODULES = (
    health,
    discovery,
    auth,
    users,
    collections,
    collection_config,
    documents,
    search,
    files,
    chunks,
    pages,
    jobs,
    limits,
    access,
    monitoring,
)


def register_all(mcp: FastMCP, sdk: DocForgeClient) -> None:
    """
    Register every DocForge tool on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (DocForgeClient): The DocForge API client injected into every tool.
    """
    # 1. Delegate to each domain module's register(mcp, sdk)
    for module in _MODULES:
        module.register(mcp, sdk)


__all__ = ["register_all"]
