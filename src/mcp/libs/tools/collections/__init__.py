# ====== Code Summary ======
# MCP tools for the collections domain — thin wrappers over sdk.collections / sdk.snippets, split
# into three cohesive groups (lifecycle, analysis, maintenance). register() calls them in this
# order, which is the order the tools appear in the MCP catalogue.

from __future__ import annotations

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from mcp.server.mcpserver import MCPServer

# ====== Local Project Imports ======
from .analysis import register_analysis_tools
from .lifecycle import register_lifecycle_tools
from .maintenance import register_maintenance_tools


def register(mcp: MCPServer, sdk: AsyncClient) -> None:
    """Register every collection tool on the MCP server, group by group.

    Args:
        mcp (MCPServer): The MCP server instance.
        sdk (AsyncClient): The DocForge API client.
    """
    register_lifecycle_tools(mcp, sdk)
    register_analysis_tools(mcp, sdk)
    register_maintenance_tools(mcp, sdk)
