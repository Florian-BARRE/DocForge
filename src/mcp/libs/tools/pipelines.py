# ====== Code Summary ======
# MCP tools for the pipelines domain — thin wrappers over sdk.pipelines: discovery + the lean
# palette/blob payload (read-only) plus the design-editing surface (inspect / edit / stage view /
# stage apply). The graph JSON stays OPAQUE at the tool boundary — blob/operations/action pass
# through as plain dicts exactly as the LLM supplies them.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP, sdk: AsyncClient) -> None:
    """Register pipeline design tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (AsyncClient): The DocForge API client.
    """

    @mcp.tool()
    async def list_pipeline_surfaces() -> Any:
        """Discover the available pipeline design surfaces (ingest / search) and their URLs."""
        result = await sdk.pipelines.list_surfaces()
        return result.model_dump(mode="json")

    @mcp.tool()
    async def get_pipeline_design(key: str, full: bool = False) -> Any:
        """
        Open a pipeline design surface: the block palette, the default blob, and any
        validation issues. `key` is "ingest" or "search"; `full=true` adds the advanced
        palette blocks (run_inputs, mechanics, artefacts).
        """
        result = await sdk.pipelines.get_design(key, full=full)
        return result.model_dump(mode="json")

    @mcp.tool()
    async def inspect_pipeline(key: str, blob: dict[str, Any]) -> Any:
        """
        Inspect an edited pipeline blob without saving it: validity, every issue found, and
        the described tree of the graph (or a build_error when it cannot even be built).
        """
        result = await sdk.pipelines.inspect(key, blob)
        return result.model_dump(mode="json")

    @mcp.tool()
    async def edit_pipeline(
        key: str, blob: dict[str, Any], operations: list[dict[str, Any]]
    ) -> Any:
        """
        Apply ordered graph operations to a pipeline blob, server-side, then build + validate
        + describe the result. Returns the edited blob (or the original one when an operation
        was impossible) plus its validity, issues, described tree and edit_error.
        """
        result = await sdk.pipelines.edit(key, blob, operations)
        return result.model_dump(mode="json")

    @mcp.tool()
    async def view_pipeline_stages(key: str, blob: dict[str, Any]) -> Any:
        """Derive the ordered stage view of a pipeline blob plus its validity verdict."""
        result = await sdk.pipelines.view_stages(key, blob)
        return result.model_dump(mode="json")

    @mcp.tool()
    async def apply_pipeline_stage(
        key: str, blob: dict[str, Any], action: dict[str, Any]
    ) -> Any:
        """
        Compile a stage-level action into a pipeline blob. Returns the recompiled blob
        (always buildable), its stage view, validity, issues and any compiler notices.
        """
        result = await sdk.pipelines.apply_stage(key, blob, action)
        return result.model_dump(mode="json")
