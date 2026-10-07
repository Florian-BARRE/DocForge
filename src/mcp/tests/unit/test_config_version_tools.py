# ====== Code Summary ======
# Wave G3: restore_config_version is confirm-gated — without confirm=true it writes nothing and returns
# the diff from the current head to the target version; with it, it forwards to the restore route.

from __future__ import annotations

# ====== Standard Library Imports ======
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from docforge_sdk.models import (
    ConfigVersionDiffResponse,
    ConfigVersionListResponse,
    ConfigVersionRestoreResponse,
    ConfigVersionSummary,
)
from mcp.server.fastmcp import FastMCP

# ====== Internal Project Imports ======
from libs.tools import config_versions

CID = "11111111-1111-1111-1111-111111111111"


def _wired() -> tuple[FastMCP, AsyncClient]:
    sdk = AsyncClient("http://localhost:8000")
    head = ConfigVersionSummary(version=5, created_at=datetime(2026, 10, 7, tzinfo=UTC))
    sdk.config_versions.list = AsyncMock(  # type: ignore[method-assign]
        return_value=ConfigVersionListResponse(
            collection_id=CID, total=5, limit=1, offset=0, items=[head]
        )
    )
    sdk.config_versions.diff = AsyncMock(  # type: ignore[method-assign]
        return_value=ConfigVersionDiffResponse(
            collection_id=CID, from_version=5, to_version=2, changes=[]
        )
    )
    sdk.config_versions.restore = AsyncMock(  # type: ignore[method-assign]
        return_value=ConfigVersionRestoreResponse(
            collection_id=CID, restored_from=2, version=6, needs_reindex=False
        )
    )
    mcp = FastMCP("t")
    config_versions.register(mcp, sdk)
    return mcp, sdk


def _fn(mcp: FastMCP, name: str) -> Any:
    tool = mcp._tool_manager.get_tool(name)
    assert tool is not None
    return tool.fn


async def test_restore_without_confirm_only_returns_the_diff_vs_head() -> None:
    mcp, sdk = _wired()
    result = await _fn(mcp, "restore_config_version")(collection_id=CID, version=2)
    assert result["restored"] is False and result["diff"]["from_version"] == 5
    cast(AsyncMock, sdk.config_versions.diff).assert_awaited_once_with(CID, 5, 2)
    cast(AsyncMock, sdk.config_versions.restore).assert_not_awaited()


async def test_restore_with_confirm_writes_a_new_version() -> None:
    mcp, sdk = _wired()
    result = await _fn(mcp, "restore_config_version")(collection_id=CID, version=2, confirm=True)
    assert result["restored"] is True and result["version"] == 6
    cast(AsyncMock, sdk.config_versions.restore).assert_awaited_once_with(CID, 2)
