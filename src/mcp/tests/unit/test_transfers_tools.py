# ====== Code Summary ======
# Unit tests for the transfers tool wrappers: export/import/get_transfer forward to their matching
# sdk.transfers method and return the model serialised as JSON; get_export_download_ref polls the
# transfer status and builds the REST download reference WITHOUT touching sdk.transfers.download_export
# (the bundle bytes are never streamed through an MCP tool result). The registered tool's raw function
# is fetched off the FastMCP instance's tool manager so the SDK call can be mocked without network I/O.

from __future__ import annotations

# ====== Standard Library Imports ======
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient, TransferAccepted, TransferStatus
from mcp.server.fastmcp import FastMCP

# ====== Internal Project Imports ======
from libs.tools import transfers as transfers_tools

CID = "22222222-2222-2222-2222-222222222222"
TID = "44444444-4444-4444-4444-444444444444"


def _register_with_fake_sdk() -> tuple[FastMCP, AsyncClient]:
    """Register the transfers tools on a bare FastMCP against a bare (unmocked) AsyncClient."""
    mcp = FastMCP(name="test")
    sdk = AsyncClient("http://localhost:8000")
    transfers_tools.register(mcp, sdk)
    return mcp, sdk


def _tool_fn(mcp: FastMCP, name: str) -> Any:
    """Fetch the raw async function backing a registered tool, bypassing MCP wire encoding."""
    tool = mcp._tool_manager.get_tool(name)
    assert tool is not None
    return tool.fn


async def test_export_collection_forwards_collection_id() -> None:
    mcp, sdk = _register_with_fake_sdk()
    export_mock = AsyncMock(
        return_value=TransferAccepted(transfer_id=TID, kind="export", status="pending")
    )
    sdk.transfers.export_collection = export_mock  # type: ignore[method-assign]
    fn = _tool_fn(mcp, "export_collection")

    result = await fn(collection_id=CID)

    export_mock.assert_awaited_once_with(CID)
    assert result["transfer_id"] == TID
    assert result["kind"] == "export"


async def test_import_collection_forwards_path_and_target_name() -> None:
    mcp, sdk = _register_with_fake_sdk()
    import_mock = AsyncMock(
        return_value=TransferAccepted(transfer_id=TID, kind="import", status="pending")
    )
    sdk.transfers.import_collection = import_mock  # type: ignore[method-assign]
    fn = _tool_fn(mcp, "import_collection")

    result = await fn(file_path="/staged/bundle.dcexport", target_name="restored")

    import_mock.assert_awaited_once_with("/staged/bundle.dcexport", target_name="restored")
    assert result["kind"] == "import"


async def test_get_transfer_returns_full_status() -> None:
    mcp, sdk = _register_with_fake_sdk()
    get_mock = AsyncMock(
        return_value=TransferStatus(
            transfer_id=TID,
            kind="export",
            status="running",
            progress=42,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    sdk.transfers.get_transfer = get_mock  # type: ignore[method-assign]
    fn = _tool_fn(mcp, "get_transfer")

    result = await fn(transfer_id=TID)

    get_mock.assert_awaited_once_with(TID)
    assert result["progress"] == 42


async def test_get_export_download_ref_builds_rest_path_without_streaming() -> None:
    mcp, sdk = _register_with_fake_sdk()
    get_mock = AsyncMock(
        return_value=TransferStatus(
            transfer_id=TID,
            kind="export",
            status="done",
            progress=100,
            size_bytes=123456,
            expires_at=datetime(2026, 9, 7, tzinfo=UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    sdk.transfers.get_transfer = get_mock  # type: ignore[method-assign]
    fn = _tool_fn(mcp, "get_export_download_ref")

    result = await fn(transfer_id=TID)

    get_mock.assert_awaited_once_with(TID)
    assert result["download_path"] == f"/api/v1/transfers/{TID}/download"
    assert result["size_bytes"] == 123456
    assert result["expires_at"] == "2026-09-07T00:00:00+00:00"
