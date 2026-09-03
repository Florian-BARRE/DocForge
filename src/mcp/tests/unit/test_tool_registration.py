# ====== Code Summary ======
# Unit test: build_mcp registers the full DocForge tool catalogue with unique names.
# Update EXPECTED_TOOL_COUNT (and the name set) whenever a tool is added or removed.

from __future__ import annotations

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient

# ====== Internal Project Imports ======
from libs.server import build_mcp

# 44 = health(1) + auth(4) + collections(9) + documents(4) + explorer(8) + search(1)
#    + jobs(5) + audit(1) + blobs(1) + pipelines(6) + transfers(4)
EXPECTED_TOOL_COUNT = 44

EXPECTED_TOOL_NAMES = {
    # health
    "ping",
    # auth
    "create_api_key",
    "list_api_keys",
    "revoke_api_key",
    "rotate_api_key",
    # collections
    "list_collections",
    "get_collection",
    "create_collection",
    "update_collection",
    "delete_collection",
    "collection_storage_footprint",
    "estimate_collection_cost",
    "export_collection_snippet",
    "apply_collection_snippet",
    # documents
    "upload_document",
    "set_document_enabled",
    "get_document_markdown",
    "get_document_html",
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
    "cancel_job",
    # audit
    "list_audit",
    # blobs
    "get_blob",
    # pipelines
    "list_pipeline_surfaces",
    "get_pipeline_design",
    "inspect_pipeline",
    "edit_pipeline",
    "view_pipeline_stages",
    "apply_pipeline_stage",
    # transfers
    "export_collection",
    "import_collection",
    "get_transfer",
    "get_export_download_ref",
}


async def test_all_tools_registered_and_unique() -> None:
    """The MCP server exposes exactly the expected number of uniquely-named tools."""
    # 1. Build the server (no network call — AsyncClient just holds a transport)
    sdk = AsyncClient("http://localhost:8000")
    mcp = build_mcp(sdk)

    # 2. Enumerate registered tools
    tools = await mcp.list_tools()
    names = [t.name for t in tools]

    # 3. Assert count + uniqueness + the exact expected name set
    assert len(names) == EXPECTED_TOOL_COUNT, f"got {len(names)} tools: {sorted(names)}"
    assert len(set(names)) == len(names), "tool names must be unique"
    assert set(names) == EXPECTED_TOOL_NAMES
