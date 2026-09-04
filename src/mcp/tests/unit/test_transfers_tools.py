# ====== Code Summary ======
# Unit tests for the transfers tool wrappers: export/import/get_transfer forward to their matching
# sdk.transfers method and return the model serialised as JSON; get_export_download_ref polls the
# transfer status and builds the REST download reference WITHOUT touching sdk.transfers.download_export
# (the bundle bytes are never streamed through an MCP tool result). The registered tool's raw function
# is fetched off the FastMCP instance's tool manager so the SDK call can be mocked without network I/O.
#
# import_collection also carries the PathGuard confinement wired in as part of the 0.14.0 audit fix
# (see test_documents_tools.py for the full path-confinement matrix); the cases here mirror it for
# this second path-based tool.

from __future__ import annotations

# ====== Standard Library Imports ======
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

# ====== Third-Party Library Imports ======
import pytest
from docforge_sdk import AsyncClient, TransferAccepted, TransferStatus
from mcp.server.fastmcp import FastMCP

# ====== Internal Project Imports ======
from libs.path_guard import PathGuard, PathGuardError
from libs.tools import transfers as transfers_tools

CID = "22222222-2222-2222-2222-222222222222"
TID = "44444444-4444-4444-4444-444444444444"

# Unconfined stand-in for stdio, used by every test not specifically exercising confinement.
_UNCONFINED_GUARD = PathGuard(confine=False, inbox_dir=None)


def _register_with_fake_sdk(
    path_guard: PathGuard = _UNCONFINED_GUARD,
) -> tuple[FastMCP, AsyncClient]:
    """Register the transfers tools on a bare FastMCP against a bare (unmocked) AsyncClient."""
    mcp = FastMCP(name="test")
    sdk = AsyncClient("http://localhost:8000")
    transfers_tools.register(mcp, sdk, path_guard)
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
    """(d) stdio (unconfined guard): an arbitrary path is forwarded to the SDK unchanged."""
    mcp, sdk = _register_with_fake_sdk()
    import_mock = AsyncMock(
        return_value=TransferAccepted(transfer_id=TID, kind="import", status="pending")
    )
    sdk.transfers.import_collection = import_mock  # type: ignore[method-assign]
    fn = _tool_fn(mcp, "import_collection")

    result = await fn(file_path="/staged/bundle.dcexport", target_name="restored")

    import_mock.assert_awaited_once_with(Path("/staged/bundle.dcexport"), target_name="restored")
    assert result["kind"] == "import"


async def test_import_collection_http_transport_path_inside_inbox_is_allowed(
    tmp_path: Path,
) -> None:
    """(a) HTTP + a path resolving inside the inbox: the SDK is called with the resolved path."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    staged = inbox / "bundle.dcexport"
    staged.write_bytes(b"dcexport-bytes")
    guard = PathGuard(confine=True, inbox_dir=inbox)
    mcp, sdk = _register_with_fake_sdk(guard)
    import_mock = AsyncMock(
        return_value=TransferAccepted(transfer_id=TID, kind="import", status="pending")
    )
    sdk.transfers.import_collection = import_mock  # type: ignore[method-assign]
    fn = _tool_fn(mcp, "import_collection")

    result = await fn(file_path=str(staged), target_name="restored")

    import_mock.assert_awaited_once_with(staged.resolve(), target_name="restored")
    assert result["kind"] == "import"


async def test_import_collection_http_transport_traversal_refused_sdk_not_called(
    tmp_path: Path,
) -> None:
    """(b) HTTP + traversal escaping the inbox: refused, sdk.transfers.import_collection unused."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (tmp_path / "secret.env").write_text("DOCFORGE_API_TOKEN=root")
    guard = PathGuard(confine=True, inbox_dir=inbox)
    mcp, sdk = _register_with_fake_sdk(guard)
    import_mock = AsyncMock()
    sdk.transfers.import_collection = import_mock  # type: ignore[method-assign]
    fn = _tool_fn(mcp, "import_collection")

    with pytest.raises(PathGuardError):
        await fn(file_path="../secret.env")

    import_mock.assert_not_awaited()


async def test_import_collection_http_transport_symlink_escape_refused_sdk_not_called(
    tmp_path: Path,
) -> None:
    """(b) HTTP + a symlink staged inside the inbox but pointing outside it: refused."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    secret = tmp_path / "secret.env"
    secret.write_text("DOCFORGE_API_TOKEN=root")
    escape_link = inbox / "looks-safe.dcexport"
    escape_link.symlink_to(secret)
    guard = PathGuard(confine=True, inbox_dir=inbox)
    mcp, sdk = _register_with_fake_sdk(guard)
    import_mock = AsyncMock()
    sdk.transfers.import_collection = import_mock  # type: ignore[method-assign]
    fn = _tool_fn(mcp, "import_collection")

    with pytest.raises(PathGuardError):
        await fn(file_path=str(escape_link))

    import_mock.assert_not_awaited()


async def test_import_collection_http_transport_no_inbox_configured_refused(
    tmp_path: Path,
) -> None:
    """(c) HTTP + no MCP_UPLOAD_DIR configured: refused regardless of path, sdk not called."""
    guard = PathGuard(confine=True, inbox_dir=None)
    mcp, sdk = _register_with_fake_sdk(guard)
    import_mock = AsyncMock()
    sdk.transfers.import_collection = import_mock  # type: ignore[method-assign]
    fn = _tool_fn(mcp, "import_collection")

    with pytest.raises(PathGuardError):
        await fn(file_path=str(tmp_path / "bundle.dcexport"))

    import_mock.assert_not_awaited()


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
