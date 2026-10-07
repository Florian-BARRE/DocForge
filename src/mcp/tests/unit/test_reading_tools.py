# ====== Code Summary ======
# Wave D (agent UX, document reading): get_document_outline / get_chunk_context / paginated
# get_document_chunks / pages on markdown+html / list_documents paging. Calls go through the real
# FastMCP dispatch; the SDK methods are mocked so forwarding (only-when-set), the text renderings
# and the total-count header are asserted without a network.

from __future__ import annotations

# ====== Standard Library Imports ======
import json
from typing import Any
from unittest.mock import AsyncMock

# ====== Third-Party Library Imports ======
import pytest
from docforge_sdk import AsyncClient
from docforge_sdk.models import (
    ChunkContext,
    ChunkInfo,
    ChunkPage,
    DocumentOutline,
    DocumentView,
)

# ====== Internal Project Imports ======
from libs.server import build_mcp

DID = "33333333-3333-3333-3333-333333333333"
CK = "44444444-4444-4444-4444-444444444444"

_OUTLINE = DocumentOutline.model_validate(
    {
        "document_id": DID,
        "display_title": "Annual Report",
        "page_count": 12,
        "headings": [
            {"level": 1, "text": "Intro", "page_number": 1, "chunk_id": CK},
            {"level": 2, "text": "Scope", "page_number": 2, "chunk_id": None},
            {"level": 1, "text": "Flat", "page_number": None, "chunk_id": None},
        ],
    }
)
_CONTEXT = ChunkContext.model_validate(
    {
        "document_id": DID,
        "display_title": "Annual Report",
        "chunks": [
            {
                "chunk_id": "a",
                "chunk_index": 3,
                "text": "before",
                "token_count": 1,
                "page_number": 4,
                "heading_path": ["Intro"],
                "is_target": False,
            },
            {
                "chunk_id": CK,
                "chunk_index": 4,
                "text": "target",
                "token_count": 1,
                "page_number": 4,
                "heading_path": ["Intro", "Scope"],
                "is_target": True,
            },
            {
                "chunk_id": "c",
                "chunk_index": 5,
                "text": "after",
                "token_count": 1,
                "page_number": None,
                "heading_path": [],
                "is_target": False,
            },
        ],
    }
)


def _chunk(index: int) -> ChunkInfo:
    # Lean wire shape: block_ids / page absent (include_geometry=false).
    return ChunkInfo.model_validate(
        {
            "id": f"c{index}",
            "chunk_index": index,
            "text": f"text {index}",
            "token_count": 7,
            "is_indexed": True,
            "role": "body",
            "enabled": True,
            "strategy": "recursive",
            "page_number": 2,
            "heading_path": ["H"],
        }
    )


def _server() -> tuple[Any, AsyncClient]:
    sdk = AsyncClient("http://localhost:8000")
    return build_mcp(sdk), sdk


async def _text(mcp: Any, name: str, args: dict[str, Any]) -> str:
    content = await mcp.call_tool(name, args)
    return str(content[0].text)


async def test_outline_text_rendering() -> None:
    mcp, sdk = _server()
    sdk.explorer.get_outline = AsyncMock(return_value=_OUTLINE)  # type: ignore[method-assign]
    text = await _text(mcp, "get_document_outline", {"document_id": DID})
    lines = text.splitlines()
    assert lines[0] == f"Annual Report | 12 pages | doc {DID} | 3 headings"
    assert lines[1] == f"Intro | p.1 | chunk {CK}"
    assert lines[2] == "  Scope | p.2"
    assert lines[3] == "Flat"
    assert text.isascii()


async def test_outline_json_format() -> None:
    mcp, sdk = _server()
    sdk.explorer.get_outline = AsyncMock(return_value=_OUTLINE)  # type: ignore[method-assign]
    data = json.loads(
        await _text(mcp, "get_document_outline", {"document_id": DID, "format": "json"})
    )
    assert data["page_count"] == 12 and len(data["headings"]) == 3


async def test_chunk_context_text_marks_target_and_forwards_window() -> None:
    mcp, sdk = _server()
    get = AsyncMock(return_value=_CONTEXT)
    sdk.explorer.get_chunk_context = get  # type: ignore[method-assign]
    text = await _text(mcp, "get_chunk_context", {"chunk_id": CK})
    assert get.call_args.args == (CK, 1, 1)
    lines = text.splitlines()
    assert lines[1:3] == ["[3] p.4 | Intro", "before"]
    assert lines[3:5] == ["[4*] p.4 | Intro > Scope", "target"]
    assert lines[5:7] == ["[5]", "after"]
    await _text(mcp, "get_chunk_context", {"chunk_id": CK, "before": 3, "after": 0})
    assert get.call_args.args == (CK, 3, 0)


async def test_chunk_context_rejects_out_of_range_window() -> None:
    mcp, _ = _server()
    with pytest.raises(Exception, match="before"):
        await mcp.call_tool("get_chunk_context", {"chunk_id": CK, "before": 6})


async def test_get_document_chunks_agent_defaults_and_total_header() -> None:
    mcp, sdk = _server()
    get = AsyncMock(return_value=ChunkPage(items=[_chunk(20), _chunk(21)], total=57))
    sdk.explorer.get_chunks_page = get  # type: ignore[method-assign]
    text = await _text(mcp, "get_document_chunks", {"document_id": DID, "offset": 20})
    assert get.call_args.args == (DID, 20, 20, False)
    lines = text.splitlines()
    assert lines[0] == "chunks 21-22 of 57"
    assert lines[1] == "[20] p.2 | H | 7 tokens | chunk c20"
    assert lines[2] == "text 20"


async def test_get_document_chunks_defaults_without_args() -> None:
    mcp, sdk = _server()
    get = AsyncMock(return_value=ChunkPage(items=[], total=0))
    sdk.explorer.get_chunks_page = get  # type: ignore[method-assign]
    text = await _text(mcp, "get_document_chunks", {"document_id": DID})
    assert get.call_args.args == (DID, 20, 0, False)
    assert text == "chunks 0 of 0"


async def test_get_document_chunks_json_omits_absent_geometry() -> None:
    mcp, sdk = _server()
    sdk.explorer.get_chunks_page = AsyncMock(  # type: ignore[method-assign]
        return_value=ChunkPage(items=[_chunk(0)], total=1)
    )
    data = json.loads(
        await _text(mcp, "get_document_chunks", {"document_id": DID, "format": "json"})
    )
    assert data["total"] == 1 and data["offset"] == 0
    assert "block_ids" not in data["chunks"][0] and "page" not in data["chunks"][0]


async def test_markdown_and_html_forward_pages_only_when_set() -> None:
    mcp, sdk = _server()
    for name, attr in (
        ("get_document_markdown", "get_markdown"),
        ("get_document_html", "get_html"),
    ):
        get = AsyncMock(return_value=DocumentView(content="x", mime_type="text/plain"))
        setattr(sdk.documents, attr, get)
        await mcp.call_tool(name, {"document_id": DID})
        assert get.call_args.kwargs == {"pages": None}
        await mcp.call_tool(name, {"document_id": DID, "pages": "5-7"})
        assert get.call_args.kwargs == {"pages": "5-7"}


async def test_list_documents_forwards_paging() -> None:
    mcp, sdk = _server()
    get = AsyncMock(return_value=[])
    sdk.explorer.list_documents = get  # type: ignore[method-assign]
    await mcp.call_tool("list_documents", {"collection_id": DID})
    assert get.call_args.args == (DID, None, None)
    await mcp.call_tool("list_documents", {"collection_id": DID, "limit": 5, "offset": 10})
    assert get.call_args.args == (DID, 5, 10)


async def test_reading_tool_descriptions_steer_agents() -> None:
    mcp, _ = _server()
    tools = {t.name: t for t in await mcp.list_tools()}
    assert "get_document_outline" in tools["get_document_markdown"].description
    assert "pages" in tools["get_document_markdown"].description
    assert "#1 way" in tools["get_chunk_context"].description
    assert "get_chunk_context" in tools["get_document_ir"].description
    assert "get_chunk_context" in tools["get_document_provenance"].description
    schema = tools["get_document_chunks"].inputSchema["properties"]
    assert schema["limit"]["default"] == 20 and schema["include_geometry"]["default"] is False
