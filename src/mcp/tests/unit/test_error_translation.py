# ====== Code Summary ======
# Unit tests for ErrorTranslatingFastMCP / translate_sdk_errors (finding 361): a failed SDK call
# must surface the API's own error body — not just the opaque status code — to the calling LLM.
# Built via build_mcp (not a bare FastMCP) so the real registration path (ErrorTranslatingFastMCP)
# is exercised, then driven through mcp.call_tool to also cover FastMCP's own wrapping layer.

from __future__ import annotations

# ====== Standard Library Imports ======
from unittest.mock import AsyncMock

# ====== Third-Party Library Imports ======
import pytest
from docforge_sdk import APIConnectionError, AsyncClient, NotFoundError
from mcp.server.fastmcp.exceptions import ToolError

# ====== Internal Project Imports ======
from libs.server import build_mcp

CID = "11111111-1111-1111-1111-111111111111"


def _build_with_failing_get_collection(exc: Exception) -> AsyncClient:
    """Build an AsyncClient whose sdk.collections.get always raises the given exception."""
    sdk = AsyncClient("http://localhost:8000")
    sdk.collections.get = AsyncMock(side_effect=exc)  # type: ignore[method-assign]
    return sdk


async def test_api_status_error_body_detail_reaches_the_tool_error() -> None:
    """A 404 with a JSON {"detail": ...} body surfaces that detail, not just the status code."""
    sdk = _build_with_failing_get_collection(
        NotFoundError(
            "API request failed with status 404",
            status_code=404,
            body={"detail": "Collection 11111111-1111-1111-1111-111111111111 not found."},
        )
    )
    mcp = build_mcp(sdk)

    with pytest.raises(ToolError) as excinfo:
        await mcp.call_tool("get_collection", {"collection_id": CID})

    message = str(excinfo.value)
    assert "404" in message
    assert "Collection 11111111-1111-1111-1111-111111111111 not found." in message


async def test_api_status_error_with_non_dict_body_is_stringified() -> None:
    """A non-JSON (plain text) error body still reaches the message, not swallowed."""
    sdk = _build_with_failing_get_collection(
        NotFoundError("API request failed with status 404", status_code=404, body="not found")
    )
    mcp = build_mcp(sdk)

    with pytest.raises(ToolError) as excinfo:
        await mcp.call_tool("get_collection", {"collection_id": CID})

    assert "not found" in str(excinfo.value)


async def test_connection_error_is_translated_too() -> None:
    """A network-level failure (no HTTP response at all) still yields a clear message."""
    sdk = _build_with_failing_get_collection(APIConnectionError("Connection refused"))
    mcp = build_mcp(sdk)

    with pytest.raises(ToolError) as excinfo:
        await mcp.call_tool("get_collection", {"collection_id": CID})

    assert "unreachable" in str(excinfo.value)
    assert "Connection refused" in str(excinfo.value)
