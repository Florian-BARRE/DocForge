# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from mcp.server.fastmcp import FastMCP

# ====== Local Project Imports ======
from . import auth, blobs, collections, documents, explorer, health, jobs, pipelines, search

# Every domain tool module, in catalogue order. Each exposes register(mcp, sdk).
_MODULES = (
    health,
    auth,
    collections,
    documents,
    explorer,
    search,
    jobs,
    blobs,
    pipelines,
)


def register_all(mcp: FastMCP, sdk: AsyncClient) -> None:
    """
    Register every DocForge tool on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (AsyncClient): The DocForge API client injected into every tool.
    """
    # 1. Delegate to each domain module's register(mcp, sdk)
    for module in _MODULES:
        module.register(mcp, sdk)


__all__ = ["register_all"]
