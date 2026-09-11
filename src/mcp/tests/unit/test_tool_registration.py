# ====== Code Summary ======
# Unit test: build_mcp registers the full DocForge tool catalogue with unique names.
# Update EXPECTED_TOOL_COUNT (and the name set) whenever a tool is added or removed.

from __future__ import annotations

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient

# ====== Internal Project Imports ======
from libs.server import build_mcp

# 66 = health(1) + capabilities(1) + auth(5) + collections(13) + documents(6) + explorer(8) + search(1)
#    + jobs(13) + audit(1) + blobs(1) + pipelines(6) + transfers(5) + corpus(4)
# collections went 10 -> 12 with collection_health + reingest_collection (finding 359, 2026-09).
# 57 -> 58 with get_capabilities, wrapping GET /capabilities (deployment self-description).
# 58 -> 62 (2026-09, remote-LLM usability audit): upload_document_bytes (documents),
# import_collection_bytes (transfers), wait_for_job + get_job_event_payload (jobs).
# 62 -> 65 (2026-09, SRE jobs-observability wave): get_failure_breakdown, get_new_failures,
# get_job_timeseries (jobs) — fleet/collection triage aggregates over sdk.jobs.
# 65 -> 66: preview_pipeline (collections) — inline non-persisting ingestion dry-run on one document.
# 66 -> 68: submit_preview_job + get_preview_job (collections) — async worker-side non-persisting
# dry-run (covers every pipeline incl. docling) + its poll.
EXPECTED_TOOL_COUNT = 68

EXPECTED_TOOL_NAMES = {
    # health
    "ping",
    # capabilities
    "get_capabilities",
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
    "preview_pipeline",
    "submit_preview_job",
    "get_preview_job",
    "export_collection_snippet",
    "apply_collection_snippet",
    "get_collection_contract_schema",
    "collection_health",
    "reingest_collection",
    # documents
    "upload_document",
    "upload_document_bytes",
    "set_document_enabled",
    "get_document_markdown",
    "get_document_html",
    "reingest_document",
    # corpus grid + bulk ops
    "query_documents",
    "delete_documents",
    "set_documents_enabled",
    "reingest_documents",
    # explorer
    "list_documents",
    "get_document",
    "get_document_pages",
    "get_document_ir",
    "get_document_provenance",
    "get_document_chunks",
    "delete_document",
    "set_chunk_enabled",
    "set_chunks_enabled",
    # search
    "search_collection",
    # jobs
    "list_jobs",
    "get_failure_breakdown",
    "get_new_failures",
    "get_job_timeseries",
    "get_job",
    "wait_for_job",
    "get_job_events",
    "get_job_event_payload",
    "get_live_workers",
    "cancel_job",
    "get_collection_cost",
    "get_queue_depth",
    "get_stage_durations",
    # auth (introspection)
    "whoami",
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
    "import_collection_bytes",
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
