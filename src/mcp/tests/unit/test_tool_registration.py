# ====== Code Summary ======
# Unit test: build_mcp registers the full DocForge tool catalogue with unique names.
# Update EXPECTED_TOOL_COUNT (and the name set) whenever a tool is added or removed.

from __future__ import annotations

# ====== Internal Project Imports ======
from libs.sdk import DocForgeClient
from libs.server import build_mcp

# 27 = health(1) + auth(3) + collections(5) + documents(2) + explorer(8) + search(1)
#    + jobs(4) + blobs(1) + pipelines(2)
EXPECTED_TOOL_COUNT = 27

EXPECTED_TOOL_NAMES = {
    # health
    "ping",
    # auth
    "create_api_key",
    "list_api_keys",
    "revoke_api_key",
    # collections
    "list_collections",
    "get_collection",
    "create_collection",
    "update_collection",
    "delete_collection",
    # documents
    "upload_document",
    "set_document_enabled",
    # explorer
    "list_documents",
    "get_document",
    "get_document_pages",
    "get_document_ir",
    "get_document_chunks",
    "delete_document",
    "set_chunk_enabled",
    "set_chunks_enabled",
    # search
    "search_collection",
    # jobs
    "list_jobs",
    "get_job",
    "get_job_events",
    "get_live_workers",
    # blobs
    "get_blob",
    # pipelines
    "list_pipeline_surfaces",
    "get_pipeline_design",
}


async def test_all_tools_registered_and_unique() -> None:
    """The MCP server exposes exactly the expected number of uniquely-named tools."""
    # 1. Build the server (no network call — DocForgeClient just holds a transport)
    sdk = DocForgeClient("http://localhost:8000")
    mcp = build_mcp(sdk)

    # 2. Enumerate registered tools
    tools = await mcp.list_tools()
    names = [t.name for t in tools]

    # 3. Assert count + uniqueness + the exact expected name set
    assert len(names) == EXPECTED_TOOL_COUNT, f"got {len(names)} tools: {sorted(names)}"
    assert len(set(names)) == len(names), "tool names must be unique"
    assert set(names) == EXPECTED_TOOL_NAMES
