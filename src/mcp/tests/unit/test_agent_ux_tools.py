# ====== Code Summary ======
# Wave A8 (agent UX): lean get_collection/list_collections, describe_collection, the typed
# search_collection schema, and unknown-argument rejection on EVERY tool (D6). Calls go through the
# real FastMCP dispatch (`mcp.call_tool`) so argument validation is exercised, not bypassed.

from __future__ import annotations

# ====== Standard Library Imports ======
import json
from typing import Any
from unittest.mock import AsyncMock

# ====== Third-Party Library Imports ======
import pytest
from docforge_sdk import AsyncClient
from docforge_sdk.models import CollectionDescription, CollectionModel, SearchResponse
from mcp.server.fastmcp.exceptions import ToolError

# ====== Internal Project Imports ======
from libs.server import build_mcp

CID = "11111111-1111-1111-1111-111111111111"

_COLLECTION = CollectionModel.model_validate(
    {
        "id": CID,
        "name": "docs",
        "supported_formats": ["pdf"],
        "max_file_size_bytes": 1,
        "needs_reindex": False,
        "pipeline": {"nodes": ["x" * 50]},
        "search": {"nodes": ["y" * 50]},
        "title_field": "title",
    }
)


async def _call(mcp: Any, name: str, args: dict[str, Any]) -> Any:
    """Call a tool through FastMCP dispatch and decode its JSON text content."""
    content = await mcp.call_tool(name, args)
    return json.loads(content[0].text)


def _server() -> tuple[Any, AsyncClient]:
    sdk = AsyncClient("http://localhost:8000")
    return build_mcp(sdk), sdk


async def test_get_collection_is_lean_by_default() -> None:
    mcp, sdk = _server()
    sdk.collections.get = AsyncMock(return_value=_COLLECTION)  # type: ignore[method-assign]
    lean = await _call(mcp, "get_collection", {"collection_id": CID})
    assert "pipeline" not in lean and "search" not in lean
    assert lean["title_field"] == "title"
    full = await _call(mcp, "get_collection", {"collection_id": CID, "include_pipelines": True})
    assert "pipeline" in full and "search" in full


async def test_describe_collection_returns_guide() -> None:
    mcp, sdk = _server()
    guide = CollectionDescription(
        collection_id=CID,
        name="docs",
        document_count=1,
        page_numbering="1-based",
        fields=[],
        searchable_targets=[],
        filter_grammar=[],
        example_requests=[],
    )
    sdk.collections.describe = AsyncMock(return_value=guide)  # type: ignore[method-assign]
    out = await _call(mcp, "describe_collection", {"collection_id": CID})
    assert out["name"] == "docs"


async def test_search_collection_forwards_typed_filters_and_targets() -> None:
    mcp, sdk = _server()
    search = AsyncMock(return_value=SearchResponse(query="q"))
    sdk.search.search = search  # type: ignore[method-assign]
    await mcp.call_tool(
        "search_collection",
        {
            "collection_id": CID,
            "query": "q",
            "filters": {"topic": "A", "year": {"gte": 2020}, "tags": ["x", "y"]},
            "search_in": [{"field": "content", "semantic": True, "lexical": False}],
        },
    )
    request = search.call_args.args[1]
    assert request.filters == {"topic": "A", "year": {"gte": 2020}, "tags": ["x", "y"]}
    assert request.search_in[0].semantic is True


async def test_search_collection_schema_is_typed() -> None:
    mcp, _ = _server()
    tool = next(t for t in await mcp.list_tools() if t.name == "search_collection")
    props = tool.inputSchema["properties"]
    assert "description" in props["filters"] and "describe_collection" in tool.description
    assert "SearchTarget" in str(tool.inputSchema)
    assert tool.inputSchema.get("additionalProperties") is False


async def test_unknown_argument_is_rejected_on_every_tool() -> None:
    mcp, _ = _server()
    for tool in await mcp.list_tools():
        assert tool.inputSchema.get("additionalProperties") is False, tool.name
    with pytest.raises(ToolError, match="page"):
        await mcp.call_tool("get_document_markdown", {"document_id": CID, "page": 5})
