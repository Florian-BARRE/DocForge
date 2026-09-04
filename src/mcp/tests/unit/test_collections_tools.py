# ====== Code Summary ======
# Unit tests for the new collections tool wrappers (finding 359): collection_health forwards
# collection_id straight through to sdk.collections.health, and reingest_collection builds a
# BulkReingestRequest (document_ids/force) and forwards it to sdk.collections.reingest. The
# registered tool's raw function is fetched off the FastMCP instance's tool manager so the SDK call
# can be mocked without any network I/O.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any
from unittest.mock import AsyncMock

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from docforge_sdk.models import BulkReingestAccepted, BulkReingestRequest, CollectionHealthResponse
from mcp.server.fastmcp import FastMCP

# ====== Internal Project Imports ======
from libs.tools import collections as collections_tools

CID = "11111111-1111-1111-1111-111111111111"


def _register_with_fake_sdk() -> tuple[FastMCP, AsyncMock, AsyncMock]:
    """Register the collections tools on a bare FastMCP against mocked health/reingest calls."""
    mcp = FastMCP(name="test")
    sdk = AsyncClient("http://localhost:8000")
    health_mock = AsyncMock(
        return_value=CollectionHealthResponse.model_validate(
            {
                "collection_id": CID,
                "verdict": "operational",
                "reason": "Everything is reachable.",
                "checked_at": "2026-09-04T00:00:00Z",
                "ingest": {"buildable": True, "providers": []},
                "search": {
                    "buildable": True,
                    "search_operational": True,
                    "providers": [],
                    "index": {"vector_count": 0},
                },
            }
        )
    )
    reingest_mock = AsyncMock(
        return_value=BulkReingestAccepted(
            collection_id=CID,
            count=0,
            matched=0,
            enqueued=0,
            capped=False,
            max_fanout=100,
            jobs=[],
        )
    )
    sdk.collections.health = health_mock  # type: ignore[method-assign]
    sdk.collections.reingest = reingest_mock  # type: ignore[method-assign]
    collections_tools.register(mcp, sdk)
    return mcp, health_mock, reingest_mock


def _tool_fn(mcp: FastMCP, name: str) -> Any:
    """Fetch the raw async function backing a registered tool, bypassing MCP wire encoding."""
    tool = mcp._tool_manager.get_tool(name)
    assert tool is not None
    return tool.fn


async def test_collection_health_forwards_collection_id() -> None:
    mcp, health_mock, _ = _register_with_fake_sdk()
    fn = _tool_fn(mcp, "collection_health")

    result = await fn(collection_id=CID)

    health_mock.assert_awaited_once_with(CID)
    assert result["collection_id"] == CID
    assert result["verdict"] == "operational"


async def test_reingest_collection_defaults_whole_collection_no_force() -> None:
    mcp, _, reingest_mock = _register_with_fake_sdk()
    fn = _tool_fn(mcp, "reingest_collection")

    result = await fn(collection_id=CID)

    reingest_mock.assert_awaited_once()
    assert reingest_mock.await_args is not None
    called_id, called_request = reingest_mock.await_args.args
    assert called_id == CID
    assert isinstance(called_request, BulkReingestRequest)
    assert called_request.document_ids is None
    assert called_request.force is False
    assert result["collection_id"] == CID


async def test_reingest_collection_forwards_subset_and_force() -> None:
    mcp, _, reingest_mock = _register_with_fake_sdk()
    fn = _tool_fn(mcp, "reingest_collection")

    await fn(collection_id=CID, document_ids=["doc-1", "doc-2"], force=True)

    assert reingest_mock.await_args is not None
    _, called_request = reingest_mock.await_args.args
    assert called_request.document_ids == ["doc-1", "doc-2"]
    assert called_request.force is True
