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
    capabilities,
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
from ._encoding import DEFAULT_MAX_INLINE_UPLOAD_BYTES

# Every domain tool module, in catalogue order. Each exposes register(mcp, sdk).
_MODULES = (
    health,
    capabilities,
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


def register_all(
    mcp: FastMCP,
    sdk: AsyncClient,
    path_guard: PathGuard,
    max_inline_upload_bytes: int = DEFAULT_MAX_INLINE_UPLOAD_BYTES,
) -> None:
    """
    Register every DocForge tool on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (AsyncClient): The DocForge API client injected into every tool.
        path_guard (PathGuard): Confines `file_path` tool arguments — passed only to the modules
            that take one (documents, transfers); every other module's signature is unchanged.
        max_inline_upload_bytes (int): Decoded-size ceiling for the bytes-based upload tools
            (`upload_document_bytes`, `import_collection_bytes`) — passed only to the same two
            path-guarded modules, which are also the only ones with a `content_base64` argument.
    """
    # 1. Delegate to each domain module's register(mcp, sdk[, path_guard, max_inline_upload_bytes])
    for module in _MODULES:
        if module in _PATH_GUARDED_MODULES:
            module.register(mcp, sdk, path_guard, max_inline_upload_bytes)
        else:
            module.register(mcp, sdk)


__all__ = ["DEFAULT_MAX_INLINE_UPLOAD_BYTES", "register_all"]
