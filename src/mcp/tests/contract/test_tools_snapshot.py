# ====== Code Summary ======
# Contract test: the tool catalogue served over the wire (tools/list, a raw JSON-RPC POST, so no
# client SDK's types are involved) equals the committed golden snapshot tools_snapshot.json - names,
# descriptions, input schemas (with additionalProperties: false) and annotations. It is the MCP
# counterpart of the OpenAPI snapshot: an SDK upgrade must leave it unchanged. After a deliberate
# catalogue change, regenerate it with `UPDATE_MCP_TOOLS_SNAPSHOT=1 uv run pytest tests/contract`.

from __future__ import annotations

# ====== Standard Library Imports ======
import json
import os
from pathlib import Path
from typing import Any

# ====== Third-Party Library Imports ======
import httpx

# ====== Internal Project Imports ======
from conftest import ContractServer

SNAPSHOT_PATH = Path(__file__).with_name("tools_snapshot.json")
_SNAPSHOT_KEYS = ("name", "description", "inputSchema", "annotations")


def _canonical(tools: list[dict[str, Any]]) -> str:
    """Canonical JSON of the catalogue: the pinned keys only, sorted by name and by key."""
    pinned = [{key: tool.get(key) for key in _SNAPSHOT_KEYS} for tool in tools]
    pinned.sort(key=lambda tool: str(tool["name"]))
    return json.dumps(pinned, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _live_tools(url: str) -> list[dict[str, Any]]:
    response = httpx.post(
        url,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={
            "Authorization": "Bearer snapshot-key",
            "Accept": "application/json, text/event-stream",
        },
    )
    response.raise_for_status()
    result = response.json()["result"]
    assert "nextCursor" not in result, "the catalogue is served in one page"
    tools: list[dict[str, Any]] = result["tools"]
    return tools


def test_live_tool_catalogue_equals_the_golden_snapshot(server: ContractServer) -> None:
    tools = _live_tools(server.url)
    live = _canonical(tools)
    if os.environ.get("UPDATE_MCP_TOOLS_SNAPSHOT") == "1":
        SNAPSHOT_PATH.write_text(live, encoding="utf-8")
    assert live == SNAPSHOT_PATH.read_text(encoding="utf-8"), (
        "tools/list drifted from tests/contract/tools_snapshot.json; regenerate it only for a "
        "deliberate catalogue change (UPDATE_MCP_TOOLS_SNAPSHOT=1)"
    )


def test_no_tool_publishes_an_output_schema_and_every_schema_forbids_extra_arguments(
    server: ContractServer,
) -> None:
    tools = _live_tools(server.url)
    assert len(tools) == 85
    for tool in tools:
        assert "outputSchema" not in tool, tool["name"]
        assert tool["inputSchema"]["additionalProperties"] is False, tool["name"]
