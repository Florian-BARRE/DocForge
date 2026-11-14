# ====== Code Summary ======
# Characterization (safety net) of the registered tool catalogue, recorded on main before the tool
# groups are reorganised (R-26). The catalogue the SERVER registers (build_mcp, no transport, no
# network) must equal the committed wire snapshot tests/contract/tools_snapshot.json - the same
# names, descriptions, input schemas and annotations the contract test pins over HTTP - so moving
# the register() closures into per-group units cannot add, drop or rename a tool, nor change a
# schema, even if the contract tests are not run. The registration ORDER (what tools/list serves
# first) is pinned separately in goldens/tool_order.json.
# After a deliberate change, regenerate with
# `UPDATE_MCP_TOOL_ORDER_GOLDEN=1 uv run pytest tests/characterization` (order) and
# `UPDATE_MCP_TOOLS_SNAPSHOT=1 uv run pytest tests/contract` (the snapshot).

from __future__ import annotations

# ====== Standard Library Imports ======
import json
import os
from pathlib import Path
from typing import Any

from recording_sdk import RecordingSdk

# ====== Internal Project Imports ======
from libs.server import build_mcp

SNAPSHOT_PATH = Path(__file__).parents[1] / "contract" / "tools_snapshot.json"
ORDER_GOLDEN_PATH = Path(__file__).with_name("goldens") / "tool_order.json"
_SNAPSHOT_KEYS = ("name", "description", "inputSchema", "annotations")


async def _registered_tools() -> list[dict[str, Any]]:
    """The catalogue as the server's tools/list serves it, in registration order."""
    mcp = build_mcp(RecordingSdk().as_client())
    tools = await mcp.list_tools()
    return [json.loads(tool.model_dump_json(by_alias=True, exclude_none=True)) for tool in tools]


async def test_registered_tools_equal_the_wire_snapshot() -> None:
    """Names, descriptions, input schemas and annotations of every tool match the snapshot."""
    live = {
        tool["name"]: {key: tool.get(key) for key in _SNAPSHOT_KEYS}
        for tool in await _registered_tools()
    }
    snapshot = {
        tool["name"]: tool for tool in json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    }
    assert sorted(live) == sorted(snapshot)
    drifted = sorted(name for name in live if live[name] != snapshot[name])
    assert drifted == [], f"tools whose definition drifted from tools_snapshot.json: {drifted}"


async def test_tool_names_are_unique_and_85_are_registered() -> None:
    names = [tool["name"] for tool in await _registered_tools()]
    assert len(names) == len(set(names)) == 85


async def test_tools_are_registered_in_the_golden_order() -> None:
    """tools/list serves the tools in registration order: a regrouping must keep it."""
    names = [tool["name"] for tool in await _registered_tools()]
    if os.environ.get("UPDATE_MCP_TOOL_ORDER_GOLDEN") == "1":
        ORDER_GOLDEN_PATH.write_text(json.dumps(names, indent=2) + "\n", encoding="utf-8")
    assert names == json.loads(ORDER_GOLDEN_PATH.read_text(encoding="utf-8")), (
        "the registration order drifted from goldens/tool_order.json; regenerate it only for a "
        "deliberate change (UPDATE_MCP_TOOL_ORDER_GOLDEN=1)"
    )
