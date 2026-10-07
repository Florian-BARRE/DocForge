# ====== Code Summary ======
# Wave C (agent UX): operator filter forms through the typed tool schema, the per-request search
# knobs (forwarded only when set), debug rendering and the browse_chunks tool.

from __future__ import annotations

# ====== Standard Library Imports ======
import json
from typing import Any
from unittest.mock import AsyncMock

# ====== Third-Party Library Imports ======
import pytest
from docforge_sdk import AsyncClient
from docforge_sdk.models import ChunkBrowseResponse, SearchResponse
from mcp.server.fastmcp.exceptions import ToolError

# ====== Internal Project Imports ======
from libs.server import build_mcp

CID = "11111111-1111-1111-1111-111111111111"

_OPERATOR_FILTERS: dict[str, Any] = {
    "a": {"contains": "MCP"},
    "b": {"not": "x"},
    "c": {"exists": True},
    "d": {"in": ["p", "q"]},
    "e": {"prefix": "AL"},
    "f": {"not_in": ["z"]},
    "g": {"eq": 3},
    "h": {"gte": 2020, "lt": "2025-01-01"},
    "i": "plain",
    "j": ["l", "m"],
}


def _server() -> tuple[Any, AsyncClient]:
    sdk = AsyncClient("http://localhost:8000")
    return build_mcp(sdk), sdk


async def test_operator_filters_forwarded_verbatim() -> None:
    mcp, sdk = _server()
    search = AsyncMock(return_value=SearchResponse(query="q"))
    sdk.search.search = search  # type: ignore[method-assign]
    await mcp.call_tool(
        "search_collection", {"collection_id": CID, "query": "q", "filters": _OPERATOR_FILTERS}
    )
    assert search.call_args.args[1].filters == _OPERATOR_FILTERS


async def test_unknown_operator_key_rejected_at_the_tool() -> None:
    mcp, sdk = _server()
    sdk.search.search = AsyncMock()  # type: ignore[method-assign]
    with pytest.raises(ToolError):
        await mcp.call_tool(
            "search_collection",
            {"collection_id": CID, "query": "q", "filters": {"k": {"bogus": 1}}},
        )
    with pytest.raises(ToolError):
        await mcp.call_tool("browse_chunks", {"collection_id": CID, "filters": {"k": {}}})
    sdk.search.search.assert_not_called()


async def test_new_knobs_not_sent_when_unset_and_sent_when_set() -> None:
    mcp, sdk = _server()
    search = AsyncMock(return_value=SearchResponse(query="q"))
    sdk.search.search = search  # type: ignore[method-assign]
    await mcp.call_tool("search_collection", {"collection_id": CID, "query": "q"})
    unset = sdk.search._search_spec(CID, search.call_args.args[1]).json
    for knob in ("min_score", "rerank", "fusion", "debug"):
        assert knob not in unset
    await mcp.call_tool(
        "search_collection",
        {
            "collection_id": CID,
            "query": "q",
            "min_score": 0.3,
            "rerank": False,
            "fusion": "dbsf",
            "debug": True,
        },
    )
    body = sdk.search._search_spec(CID, search.call_args.args[1]).json
    assert (body["min_score"], body["rerank"], body["fusion"], body["debug"]) == (
        0.3,
        False,
        "dbsf",
        True,
    )


async def test_debug_scores_rendered_on_citation_line() -> None:
    mcp, sdk = _server()
    sdk.search.search = AsyncMock(  # type: ignore[method-assign]
        return_value=SearchResponse.model_validate(
            {
                "query": "q",
                "hits": [
                    {
                        "chunk_id": "c1",
                        "document_id": "d1",
                        "text": "t",
                        "fusion_score": 0.5,
                        "rerank_score": 0.9,
                    }
                ],
            }
        )
    )
    out = await mcp.call_tool(
        "search_collection", {"collection_id": CID, "query": "q", "debug": True}
    )
    assert "fusion 0.500 / rerank 0.900" in str(out)


_PAGE: dict[str, Any] = {
    "chunks": [
        {
            "chunk_id": "c1",
            "document_id": "d1",
            "document_title": "Report",
            "page_number": 2,
            "heading_path": ["Intro"],
            "text": "First passage.",
        }
    ],
    "next_cursor": "tok1",
    "hints": [{"field": "f", "value": "v", "message": "No doc has f=v", "suggestions": []}],
}


async def test_browse_text_json_and_cursor_follow() -> None:
    mcp, sdk = _server()
    browse = AsyncMock(
        side_effect=[
            ChunkBrowseResponse.model_validate(_PAGE),
            ChunkBrowseResponse(chunks=[], next_cursor=None),
        ]
    )
    sdk.search.browse = browse  # type: ignore[method-assign]
    first = str(
        await mcp.call_tool(
            "browse_chunks", {"collection_id": CID, "filters": {"topic": "x"}, "limit": 1}
        )
    )
    assert "[1] Report | p.2 | Intro | doc d1 | chunk c1" in first
    assert "First passage." in first and "next_cursor: tok1" in first and "Hint: No doc" in first
    request = browse.call_args.args[1]
    assert request.cursor is None and "score" not in request.return_fields

    last = str(
        await mcp.call_tool(
            "browse_chunks",
            {"collection_id": CID, "filters": {"topic": "x"}, "cursor": "tok1"},
        )
    )
    assert browse.call_args.args[1].cursor == "tok1" and "end of results" in last


async def test_browse_json_is_compact() -> None:
    mcp, sdk = _server()
    sdk.search.browse = AsyncMock(  # type: ignore[method-assign]
        return_value=ChunkBrowseResponse.model_validate(_PAGE)
    )
    out = await mcp.call_tool("browse_chunks", {"collection_id": CID, "format": "json"})
    payload = _first_text(out)
    assert "\n" not in payload and ", " not in payload
    assert json.loads(payload)["next_cursor"] == "tok1"


def _first_text(result: Any) -> str:
    """Extract the tool's text payload from FastMCP's (content, structured) result shapes."""
    content = result[0] if isinstance(result, tuple) else result
    return str(content[0].text)
