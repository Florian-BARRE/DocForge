# ====== Code Summary ======
# Unit tests for the documents tool wrappers, focused on the PathGuard confinement wired into
# upload_document (0.14.0 audit fix): on streamable-HTTP the tool must only ever call
# sdk.documents.upload with a path inside the configured inbox, refusing traversal/absolute-escape
# and refusing everything when no inbox is configured; on stdio the pre-fix arbitrary-path behaviour
# is preserved. The registered tool's raw function is fetched off the FastMCP instance's tool
# manager so the SDK call can be mocked without any network I/O.

from __future__ import annotations

# ====== Standard Library Imports ======
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

# ====== Third-Party Library Imports ======
import pytest
from docforge_sdk import AsyncClient, UploadAccepted
from mcp.server.fastmcp import FastMCP

# ====== Internal Project Imports ======
from libs.path_guard import PathGuard, PathGuardError
from libs.tools import documents as documents_tools

CID = "11111111-1111-1111-1111-111111111111"
DID = "33333333-3333-3333-3333-333333333333"
JID = "55555555-5555-5555-5555-555555555555"


def _register(path_guard: PathGuard) -> tuple[FastMCP, AsyncMock]:
    """Register the documents tools on a bare FastMCP with a mocked sdk.documents.upload."""
    mcp = FastMCP(name="test")
    sdk = AsyncClient("http://localhost:8000")
    upload_mock = AsyncMock(
        return_value=UploadAccepted(document_id=DID, job_id=JID, duplicate=False)
    )
    sdk.documents.upload = upload_mock  # type: ignore[method-assign]
    documents_tools.register(mcp, sdk, path_guard)
    return mcp, upload_mock


def _tool_fn(mcp: FastMCP, name: str) -> Any:
    """Fetch the raw async function backing a registered tool, bypassing MCP wire encoding."""
    tool = mcp._tool_manager.get_tool(name)
    assert tool is not None
    return tool.fn


async def test_http_transport_path_inside_inbox_is_allowed(tmp_path: Path) -> None:
    """(a) HTTP + a path resolving inside the inbox: the SDK is called with the resolved path."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    staged = inbox / "report.pdf"
    staged.write_bytes(b"%PDF-1.4")
    guard = PathGuard(confine=True, inbox_dir=inbox)
    mcp, upload_mock = _register(guard)
    fn = _tool_fn(mcp, "upload_document")

    result = await fn(file_path=str(staged), collection_id=CID)

    upload_mock.assert_awaited_once_with(CID, staged.resolve(), metadata=None)
    assert result["document_id"] == DID


@pytest.mark.parametrize(
    "bad_path_factory",
    [
        lambda tmp_path, inbox: "../secret.env",
        lambda tmp_path, inbox: str(tmp_path / "secret.env"),
    ],
    ids=["traversal", "absolute-outside"],
)
async def test_http_transport_escaping_path_is_refused_sdk_never_called(
    tmp_path: Path, bad_path_factory: Any
) -> None:
    """(b) HTTP + traversal/absolute-outside path: refused, sdk.documents.upload never awaited."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (tmp_path / "secret.env").write_text("DOCFORGE_API_TOKEN=root")
    guard = PathGuard(confine=True, inbox_dir=inbox)
    mcp, upload_mock = _register(guard)
    fn = _tool_fn(mcp, "upload_document")

    with pytest.raises(PathGuardError):
        await fn(file_path=bad_path_factory(tmp_path, inbox), collection_id=CID)

    upload_mock.assert_not_awaited()


async def test_http_transport_symlink_escape_is_refused_sdk_never_called(tmp_path: Path) -> None:
    """(b) HTTP + a symlink staged inside the inbox but pointing outside it: refused."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    secret = tmp_path / "secret.env"
    secret.write_text("DOCFORGE_API_TOKEN=root")
    escape_link = inbox / "looks-safe.pdf"
    escape_link.symlink_to(secret)
    guard = PathGuard(confine=True, inbox_dir=inbox)
    mcp, upload_mock = _register(guard)
    fn = _tool_fn(mcp, "upload_document")

    with pytest.raises(PathGuardError):
        await fn(file_path=str(escape_link), collection_id=CID)

    upload_mock.assert_not_awaited()


async def test_http_transport_with_no_inbox_configured_is_refused(tmp_path: Path) -> None:
    """(c) HTTP + no MCP_UPLOAD_DIR configured: refused regardless of the path, sdk not called."""
    guard = PathGuard(confine=True, inbox_dir=None)
    mcp, upload_mock = _register(guard)
    fn = _tool_fn(mcp, "upload_document")

    with pytest.raises(PathGuardError):
        await fn(file_path=str(tmp_path / "anything.pdf"), collection_id=CID)

    upload_mock.assert_not_awaited()


async def test_stdio_transport_allows_arbitrary_local_path_unchanged(tmp_path: Path) -> None:
    """(d) stdio (confine=False): an arbitrary local path is forwarded to the SDK unchanged."""
    guard = PathGuard(confine=False, inbox_dir=None)
    mcp, upload_mock = _register(guard)
    fn = _tool_fn(mcp, "upload_document")
    outside = tmp_path / "elsewhere" / "doc.pdf"

    result = await fn(file_path=str(outside), collection_id=CID)

    upload_mock.assert_awaited_once_with(CID, Path(str(outside)), metadata=None)
    assert result["document_id"] == DID
