# ====== Code Summary ======
# MCP tools for the blobs domain — thin wrapper over sdk.blobs. Image blobs (page renders,
# figure crops) are returned as an inline MCP Image; every other mime type (original upload,
# canonical PDF) is returned base64-encoded alongside its mime_type.

from __future__ import annotations

# ====== Standard Library Imports ======
import base64
from typing import Any

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from mcp.server.fastmcp import FastMCP, Image


def register(mcp: FastMCP, sdk: AsyncClient) -> None:
    """Register blob tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (AsyncClient): The DocForge API client.
    """

    @mcp.tool()
    async def get_blob(content_hash: str) -> Any:
        """
        Fetch a content-addressed blob's bytes (page render, figure crop, canonical PDF,
        original upload). Image blobs are returned as an inline image; every other mime type
        is returned base64-encoded alongside its mime_type.
        """
        blob = await sdk.blobs.get(content_hash)
        if blob.mime_type.startswith("image/"):
            return Image(data=blob.content, format=blob.mime_type.split("/", 1)[-1])
        return {"mime_type": blob.mime_type, "content_base64": base64.b64encode(blob.content).decode()}
