# ====== Code Summary ======
# Characterization (safety net) of the tool -> SDK call mapping, recorded on main before the tool
# groups are reorganised (R-26). Every case of tool_call_cases.CASES invokes a tool through the
# real server (build_mcp: argument validation, error translation, registration wiring) against a
# recording stub SDK; the golden goldens/tool_sdk_calls.json pins, per case, which
# `sdk.<resource>.<method>` the tool calls, in which order, and the exact positional/keyword
# arguments it builds (typed requests keep their class name and the fields the tool set). A
# refactor that renames a method, drops a keyword, reshapes a request or skips a confirmation gate
# fails here. What a tool does with the SDK's RESPONSE is pinned only where a case scripts one.
# After a deliberate change, regenerate with
# `UPDATE_MCP_TOOL_CALLS_GOLDEN=1 uv run pytest tests/characterization` and review the diff.

from __future__ import annotations

# ====== Standard Library Imports ======
import asyncio
import json
import os
from pathlib import Path
from typing import Any

# ====== Third-Party Library Imports ======
import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import UnexpectedToolError
from recording_sdk import RecordingSdk, StubSdkCallRecorded
from tool_call_cases import CASES, ToolCase

# ====== Internal Project Imports ======
from libs.path_guard import PathGuard
from libs.server import build_mcp

GOLDEN_PATH = Path(__file__).with_name("goldens") / "tool_sdk_calls.json"


def _build_server(sdk: RecordingSdk) -> MCPServer:
    """The production server over the stub; path tools run unconfined (stdio), like a local run."""
    return build_mcp(sdk.as_client(), PathGuard(confine=False, inbox_dir=None))


async def _record(server: MCPServer, sdk: RecordingSdk, case: ToolCase) -> dict[str, Any]:
    """Run one case against the shared server (the stub is reset first); return its golden entry."""
    sdk.calls.clear()
    sdk.returns = case.returns() if case.returns else {}
    entry: dict[str, Any] = {"tool": case.tool, "arguments": case.arguments}
    try:
        result = await server.call_tool(case.tool, case.arguments)
    except UnexpectedToolError as exc:
        # The stub ended the run after the tool's last unscripted SDK call; anything else is a
        # tool failure the golden must not silently absorb.
        assert isinstance(exc.__cause__, StubSdkCallRecorded), f"{case.case_id}: {exc!r}"
        entry["completed"] = False
    else:
        entry["completed"] = True
        entry["result"] = json.loads(result.model_dump_json(by_alias=True, exclude_none=True))
    entry["calls"] = [call.as_json() for call in sdk.calls]
    return entry


async def _record_all() -> dict[str, Any]:
    """Every case's golden entry, keyed by case id."""
    sdk = RecordingSdk()
    server = _build_server(sdk)
    return {case.case_id: await _record(server, sdk, case) for case in CASES}


@pytest.fixture(scope="module")
def recorded() -> dict[str, Any]:
    """Today's tool -> SDK calls, as JSON data; rewrites the golden when asked to."""
    live: dict[str, Any] = json.loads(json.dumps(asyncio.run(_record_all())))
    if os.environ.get("UPDATE_MCP_TOOL_CALLS_GOLDEN") == "1":
        GOLDEN_PATH.write_text(
            json.dumps(live, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return live


@pytest.fixture(scope="module")
def golden() -> dict[str, Any]:
    """The committed golden, read after `recorded` had its chance to regenerate it."""
    data: dict[str, Any] = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    return data


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_tool_maps_to_the_golden_sdk_calls(
    case: ToolCase, recorded: dict[str, Any], golden: dict[str, Any]
) -> None:
    assert case.case_id in golden, f"{case.case_id}: no golden entry; regenerate the golden"
    assert recorded[case.case_id] == golden[case.case_id], (
        f"{case.case_id}: the tool's SDK calls drifted from goldens/tool_sdk_calls.json; "
        "regenerate it only for a deliberate change (UPDATE_MCP_TOOL_CALLS_GOLDEN=1)"
    )


def test_every_case_calls_the_sdk(recorded: dict[str, Any]) -> None:
    """A case that never reached the SDK (a validation error, say) would pin nothing."""
    silent = [case_id for case_id, entry in recorded.items() if not entry["calls"]]
    assert silent == []


def test_case_ids_are_unique() -> None:
    ids = [case.case_id for case in CASES]
    assert len(ids) == len(set(ids))


async def test_every_registered_tool_has_a_case() -> None:
    """A tool added to (or dropped from) the catalogue must be added to (or dropped from) the cases."""
    registered = {tool.name for tool in await _build_server(RecordingSdk()).list_tools()}
    assert {case.tool for case in CASES} == registered


def test_the_golden_holds_no_stale_case(golden: dict[str, Any]) -> None:
    assert set(golden) == {case.case_id for case in CASES}
