# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from mcp.server.fastmcp import FastMCP

# ====== Local Project Imports ======
from ..sdk import DocForgeClient
from . import (
    chunks,
    collection_config,
    collections,
    discovery,
    documents,
    files,
    health,
    jobs,
    monitoring,
    pages,
    search,
)

# Every domain tool module, in catalogue order. Each exposes register(mcp, sdk).
_MODULES = (
    health,
    discovery,
    collections,
    collection_config,
    documents,
    search,
    files,
    chunks,
    pages,
    jobs,
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
