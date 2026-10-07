# ====== Code Summary ======
# Wave G1: set_collection_alias creates a new alias directly, previews a re-point (old → new) without
# confirm=true and forwards it with confirm=true; delete_collection_alias forwards to the SDK.

from __future__ import annotations

# ====== Standard Library Imports ======
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from docforge_sdk.models import CollectionAliasModel, SetCollectionAliasResponse
from mcp.server.fastmcp import FastMCP

# ====== Internal Project Imports ======
from libs.tools import collection_aliases

NOW = datetime(2026, 10, 7, tzinfo=UTC)
_A = CollectionAliasModel(
    name="chatmop", collection_id="c-1", collection_name="v1", created_at=NOW, updated_at=NOW
)


def _wired(existing: list[CollectionAliasModel]) -> tuple[FastMCP, AsyncClient]:
    sdk = AsyncClient("http://localhost:8000")
    sdk.collection_aliases.list = AsyncMock(return_value=existing)  # type: ignore[method-assign]
    sdk.collection_aliases.set = AsyncMock(  # type: ignore[method-assign]
        return_value=SetCollectionAliasResponse(
            name="chatmop", collection_id="c-2", collection_name="v2", created_at=NOW,
            updated_at=NOW, previous_collection_id="c-1", created=False,
        )
    )  # fmt: skip
    sdk.collection_aliases.delete = AsyncMock(return_value=None)  # type: ignore[method-assign]
    mcp = FastMCP("t")
    collection_aliases.register(mcp, sdk)
    return mcp, sdk


async def _call(mcp: FastMCP, name: str, args: dict[str, Any]) -> Any:
    tool = mcp._tool_manager.get_tool(name)
    assert tool is not None
    return await tool.fn(**args)


async def test_repoint_without_confirm_is_a_preview() -> None:
    mcp, sdk = _wired([_A])
    result = await _call(mcp, "set_collection_alias", {"name": "chatmop", "collection_id": "c-2"})
    assert result["applied"] is False and result["from_collection_id"] == "c-1"
    cast(AsyncMock, sdk.collection_aliases.set).assert_not_called()


async def test_repoint_with_confirm_and_create_write() -> None:
    mcp, sdk = _wired([_A])
    args = {"name": "chatmop", "collection_id": "c-2", "confirm": True}
    assert (await _call(mcp, "set_collection_alias", args))["applied"] is True
    mcp2, sdk2 = _wired([])
    created = await _call(mcp2, "set_collection_alias", {"name": "new", "collection_id": "c-2"})
    assert created["applied"] is True
    cast(AsyncMock, sdk2.collection_aliases.set).assert_awaited_once_with("new", "c-2")


async def test_delete_forwards() -> None:
    mcp, sdk = _wired([_A])
    assert (await _call(mcp, "delete_collection_alias", {"name": "chatmop"}))["deleted"] is True
    cast(AsyncMock, sdk.collection_aliases.delete).assert_awaited_once_with("chatmop")
