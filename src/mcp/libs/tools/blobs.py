# ====== Code Summary ======
# MCP tools for the blobs domain — thin wrapper over sdk.blobs. Image blobs (page renders,
# figure crops) are returned as an inline MCP Image; every other mime type (original upload,
# canonical PDF) is returned base64-encoded alongside its mime_type.

from __future__ import annotations

# ====== Standard Library Imports ======
import base64
from typing import Any

# ====== Third-Party Library Imports ======
from mcp.server.fastmcp import FastMCP, Image

# ====== Local Project Imports ======
from ..sdk import DocForgeClient


def register(mcp: FastMCP, sdk: DocForgeClient) -> None:
    """Register blob tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (DocForgeClient): The DocForge API client.
    """

    @mcp.tool()
    async def get_blob(content_hash: str) -> Any:
        """
        Fetch a content-addressed blob's bytes (page render, figure crop, canonical PDF,
        original upload). Image blobs are returned as an inline image; every other mime type
        is returned base64-encoded alongside its mime_type.
        """
        data, mime_type = await sdk.blobs.get(content_hash)
        if mime_type.startswith("image/"):
            return Image(data=data, format=mime_type.split("/", 1)[-1])
        return {"mime_type": mime_type, "content_base64": base64.b64encode(data).decode()}
