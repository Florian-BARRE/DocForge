# ====== Code Summary ======
# Unit test: build_mcp registers the full DocForge tool catalogue with unique names.
# Update EXPECTED_TOOL_COUNT whenever a tool is added or removed.

from __future__ import annotations

# ====== Internal Project Imports ======
from libs.sdk import DocForgeClient
from libs.server import build_mcp

# 51 = health(1) + discovery(1) + auth(5) + users(4) + collections(3) + config(5)
#    + documents(6) + search(2) + files(4) + chunks(3) + pages(4) + jobs(3)
#    + limits(2) + access(3) + monitoring(5)
EXPECTED_TOOL_COUNT = 51


async def test_all_tools_registered_and_unique() -> None:
    """The MCP server exposes exactly the expected number of uniquely-named tools."""
    # 1. Build the server (no network call — DocForgeClient just holds a transport)
    sdk = DocForgeClient("http://localhost:8000")
    mcp = build_mcp(sdk)

    # 2. Enumerate registered tools
    tools = await mcp.list_tools()
    names = [t.name for t in tools]

    # 3. Assert count + uniqueness
    assert len(names) == EXPECTED_TOOL_COUNT, f"got {len(names)} tools: {sorted(names)}"
    assert len(set(names)) == len(names), "tool names must be unique"
