# ====== Code Summary ======
# Unit tests for the jobs tool wrappers: cancel_job forwards job_id/force to sdk.jobs.cancel and
# returns the CancelResult serialised as JSON. The registered tool's raw function is fetched off
# the FastMCP instance's tool manager so the SDK call can be mocked without any network I/O.

from __future__ import annotations

# ====== Standard Library Imports ======
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient, CancelResult, JobEventPayload, JobStatus
from mcp.server.fastmcp import FastMCP

# ====== Internal Project Imports ======
from libs.tools import jobs as jobs_tools

JID = "55555555-5555-5555-5555-555555555555"
EID = "66666666-6666-6666-6666-666666666666"


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


def _job_status(status: str) -> JobStatus:
    """Build a minimal JobStatus for the given status string."""
    return JobStatus(
        job_id=JID,
        document_id="33333333-3333-3333-3333-333333333333",
        collection_id="11111111-1111-1111-1111-111111111111",
        status=status,
        cancel_requested=False,
        progress=0,
        attempt=1,
        updated_at=datetime.now(UTC),
        stalled=False,
        total_prompt_tokens=0,
        total_completion_tokens=0,
        cost_usd=0.0,
    )


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


async def test_wait_for_job_returns_immediately_once_terminal() -> None:
    """A job already terminal on the first poll returns without sleeping."""
    mcp = FastMCP(name="test")
    sdk = AsyncClient("http://localhost:8000")
    get_mock = AsyncMock(return_value=_job_status("done"))
    sdk.jobs.get = get_mock  # type: ignore[method-assign]
    jobs_tools.register(mcp, sdk)
    fn = _tool_fn(mcp, "wait_for_job")

    with patch("libs.tools.jobs.asyncio.sleep", new_callable=AsyncMock) as sleep_mock:
        result = await fn(job_id=JID)

    get_mock.assert_awaited_once_with(JID)
    sleep_mock.assert_not_awaited()
    assert result["status"] == "done"


async def test_wait_for_job_polls_until_terminal() -> None:
    """A non-terminal first poll is followed by a sleep, then a second (terminal) poll."""
    mcp = FastMCP(name="test")
    sdk = AsyncClient("http://localhost:8000")
    get_mock = AsyncMock(side_effect=[_job_status("running"), _job_status("done")])
    sdk.jobs.get = get_mock  # type: ignore[method-assign]
    jobs_tools.register(mcp, sdk)
    fn = _tool_fn(mcp, "wait_for_job")

    with patch("libs.tools.jobs.asyncio.sleep", new_callable=AsyncMock) as sleep_mock:
        result = await fn(job_id=JID)

    assert get_mock.await_count == 2
    sleep_mock.assert_awaited_once()
    assert result["status"] == "done"


async def test_wait_for_job_returns_non_terminal_status_once_timeout_elapses() -> None:
    """timeout_s=0 means the deadline has already passed after the first poll: no sleep, no loop."""
    mcp = FastMCP(name="test")
    sdk = AsyncClient("http://localhost:8000")
    get_mock = AsyncMock(return_value=_job_status("running"))
    sdk.jobs.get = get_mock  # type: ignore[method-assign]
    jobs_tools.register(mcp, sdk)
    fn = _tool_fn(mcp, "wait_for_job")

    with patch("libs.tools.jobs.asyncio.sleep", new_callable=AsyncMock) as sleep_mock:
        result = await fn(job_id=JID, timeout_s=0)

    get_mock.assert_awaited_once_with(JID)
    sleep_mock.assert_not_awaited()
    assert result["status"] == "running"


async def test_wait_for_job_clamps_sleep_to_remaining_deadline() -> None:
    """The inter-poll sleep is clamped to whatever's left of timeout_s, never overshooting it."""
    mcp = FastMCP(name="test")
    sdk = AsyncClient("http://localhost:8000")
    get_mock = AsyncMock(side_effect=[_job_status("running"), _job_status("done")])
    sdk.jobs.get = get_mock  # type: ignore[method-assign]
    jobs_tools.register(mcp, sdk)
    fn = _tool_fn(mcp, "wait_for_job")

    # monotonic() is read once to set the deadline (0.0 -> deadline 1.0), then once per loop
    # iteration to compute what's left. At 0.75s in, only 0.25s remains — less than the initial
    # 0.5s backoff delay — so the sleep must be clamped to that 0.25s, not the full 0.5s.
    with (
        patch("libs.tools.jobs.time.monotonic", side_effect=[0.0, 0.75, 1.0]),
        patch("libs.tools.jobs.asyncio.sleep", new_callable=AsyncMock) as sleep_mock,
    ):
        result = await fn(job_id=JID, timeout_s=1.0)

    sleep_mock.assert_awaited_once_with(0.25)
    assert result["status"] == "done"


def test_wait_for_job_cap_stays_under_a_standard_client_sse_read_timeout() -> None:
    """
    Regression guard: _MAX_WAIT_TIMEOUT_S must stay strictly below 300s (a standard MCP client's
    default sse_read_timeout) or a long-running wait_for_job call would have its connection severed
    by the client before this stateless_http+json_response server ever gets to respond (see the
    constant's docstring in libs/tools/jobs.py for the full mechanism).
    """
    assert jobs_tools._MAX_WAIT_TIMEOUT_S < 300.0


async def test_wait_for_job_clamps_a_timeout_above_the_hard_cap() -> None:
    """
    A caller-supplied timeout_s far above the hard cap is clamped down to it, not honoured as-is:
    the deadline is set from _MAX_WAIT_TIMEOUT_S (240s), so a clock jump past that (but nowhere
    near the caller's requested 10_000s) still ends the loop.
    """
    mcp = FastMCP(name="test")
    sdk = AsyncClient("http://localhost:8000")
    get_mock = AsyncMock(return_value=_job_status("running"))
    sdk.jobs.get = get_mock  # type: ignore[method-assign]
    jobs_tools.register(mcp, sdk)
    fn = _tool_fn(mcp, "wait_for_job")

    # monotonic(): 0.0 sets the deadline (-> 240.0), 0.0 is the first in-loop check (not yet past
    # the deadline, so one sleep happens), 500.0 is the second in-loop check — past the 240.0
    # deadline but nowhere near an uncapped 10_000.0 one, proving the clamp took effect.
    with (
        patch("libs.tools.jobs.time.monotonic", side_effect=[0.0, 0.0, 500.0]),
        patch("libs.tools.jobs.asyncio.sleep", new_callable=AsyncMock) as sleep_mock,
    ):
        result = await fn(job_id=JID, timeout_s=10_000.0)

    assert get_mock.await_count == 2
    sleep_mock.assert_awaited_once_with(jobs_tools._POLL_INITIAL_DELAY_S)
    assert result["status"] == "running"


async def test_get_job_event_payload_forwards_args_and_defaults_slot_to_output() -> None:
    mcp = FastMCP(name="test")
    sdk = AsyncClient("http://localhost:8000")
    payload_mock = AsyncMock(
        return_value=JobEventPayload(
            job_id=JID,
            event_id=EID,
            slot="output",
            stage="parse",
            truncated=False,
            size_bytes=42,
            payload={"ok": True},
        )
    )
    sdk.jobs.get_event_payload = payload_mock  # type: ignore[method-assign]
    jobs_tools.register(mcp, sdk)
    fn = _tool_fn(mcp, "get_job_event_payload")

    result = await fn(job_id=JID, event_id=EID)

    payload_mock.assert_awaited_once_with(JID, EID, slot="output")
    assert result["payload"] == {"ok": True}
