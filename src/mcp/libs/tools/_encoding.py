# ====== Code Summary ======
# Shared base64 decoding for the two bytes-based upload tools (upload_document_bytes,
# import_collection_bytes) — both need the exact same "decode, cap, or raise an actionable
# ToolError" behaviour, so it lives once here instead of being duplicated per tool module.
# The size cap (MCP_MAX_INLINE_UPLOAD_BYTES) exists because base64.b64decode materializes the
# whole payload in memory before any server-side size check ever runs — an inline upload with no
# ceiling of its own is an easy way for one caller to OOM the MCP process. A caller that needs to
# move more than the cap allows should use the path-based tool (upload_document / import_collection)
# against a staged file instead — the SDK streams those from disk.

from __future__ import annotations

# ====== Standard Library Imports ======
import base64
import binascii

# ====== Third-Party Library Imports ======
from mcp.server.fastmcp.exceptions import ToolError

# Fallback cap used only when a caller doesn't thread McpConfig.MCP_MAX_INLINE_UPLOAD_BYTES through
# (e.g. a test building tools directly) — mirrors the config default (100 MiB).
DEFAULT_MAX_INLINE_UPLOAD_BYTES = 100 * 1024 * 1024


def decode_base64_arg(
    content_base64: str, max_bytes: int = DEFAULT_MAX_INLINE_UPLOAD_BYTES
) -> bytes:
    """
    Decode a tool-supplied base64 payload, capping its decoded size.

    Args:
        content_base64 (str): Raw bytes, standard base64-encoded.
        max_bytes (int): The decoded payload must not exceed this many bytes (operator-configured
            via `MCP_MAX_INLINE_UPLOAD_BYTES`).

    Returns:
        bytes: The decoded content.

    Raises:
        ToolError: `content_base64` is not valid base64, or the decoded payload exceeds `max_bytes`.
    """
    try:
        decoded = base64.b64decode(content_base64, validate=True)
    except binascii.Error as exc:
        raise ToolError(f"content_base64 is not valid base64: {exc}") from exc

    if len(decoded) > max_bytes:
        raise ToolError(
            f"Decoded payload is {len(decoded)} bytes, over this deployment's "
            f"{max_bytes}-byte inline-upload cap (MCP_MAX_INLINE_UPLOAD_BYTES). For a larger "
            "file, stage it on the MCP server's filesystem (MCP_UPLOAD_DIR) and use the "
            "path-based upload_document / import_collection tool instead."
        )
    return decoded


__all__ = ["DEFAULT_MAX_INLINE_UPLOAD_BYTES", "decode_base64_arg"]
