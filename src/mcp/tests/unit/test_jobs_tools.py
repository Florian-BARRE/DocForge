# ====== Code Summary ======
# Unit tests for the jobs tool wrappers: cancel_job forwards job_id/force to sdk.jobs.cancel and
# returns the CancelResult serialised as JSON. The registered tool's raw function is fetched off
# the FastMCP instance's tool manager so the SDK call can be mocked without any network I/O.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any
from unittest.mock import AsyncMock

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient, CancelResult
from mcp.server.fastmcp import FastMCP

# ====== Internal Project Imports ======
from libs.tools import jobs as jobs_tools

JID = "55555555-5555-5555-5555-555555555555"


def _register_with_fake_sdk() -> tuple[FastMCP, AsyncMock]:
    """Register the jobs tools on a bare FastMCP against a mocked sdk.jobs.cancel."""
    mcp = FastMCP(name="test")
    sdk = AsyncClient("http://localhost:8000")
    cancel_mock = AsyncMock(
        return_value=CancelResult(
            job_id=JID,
            status="running",
            cancel_requested=True,
            outcome="cancellation_requested",
            detail="Cooperative cancellation requested.",
        )
    )
    sdk.jobs.cancel = cancel_mock  # type: ignore[method-assign]
    jobs_tools.register(mcp, sdk)
    return mcp, cancel_mock


def _tool_fn(mcp: FastMCP, name: str) -> Any:
    """Fetch the raw async function backing a registered tool, bypassing MCP wire encoding."""
    tool = mcp._tool_manager.get_tool(name)
    assert tool is not None
    return tool.fn


async def test_cancel_job_defaults_force_false_and_forwards_job_id() -> None:
    mcp, cancel_mock = _register_with_fake_sdk()
    fn = _tool_fn(mcp, "cancel_job")

    result = await fn(job_id=JID)

    cancel_mock.assert_awaited_once_with(JID, force=False)
    assert result["outcome"] == "cancellation_requested"
    assert result["cancel_requested"] is True


async def test_cancel_job_forwards_force_true() -> None:
    mcp, cancel_mock = _register_with_fake_sdk()
    fn = _tool_fn(mcp, "cancel_job")

    await fn(job_id=JID, force=True)

    cancel_mock.assert_awaited_once_with(JID, force=True)
