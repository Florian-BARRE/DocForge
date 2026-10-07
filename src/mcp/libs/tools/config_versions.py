# ====== Code Summary ======
# MCP tools for a collection's versioned config history — a thin wrapper over sdk.config_versions:
# list, read (secrets masked), diff, and a CONFIRM-gated restore (without confirm=true it only returns
# the diff the restore would apply vs the current head, so an LLM sees the change before making it).

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP, sdk: AsyncClient) -> None:
    """Register the config-history tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (AsyncClient): The DocForge API client.
    """

    @mcp.tool()
    async def list_config_versions(collection_id: str, limit: int = 20, offset: int = 0) -> Any:
        """List a collection's pipeline/search config versions, newest first: version, date, note,
        author (key name / "root" / "anonymous") and `changes` (which pipeline nodes / search
        changed vs the previous version). Page with `limit`/`offset`; `total` is the full count."""
        page = await sdk.config_versions.list(collection_id, limit=limit, offset=offset)
        return page.model_dump(mode="json")

    @mcp.tool()
    async def get_config_version(collection_id: str, version: int) -> Any:
        """Read one config version: its {pipeline, search} snapshot with every secret masked."""
        detail = await sdk.config_versions.get(collection_id, version)
        return detail.model_dump(mode="json")

    @mcp.tool()
    async def diff_config_versions(collection_id: str, from_version: int, to_version: int) -> Any:
        """Diff two config versions: added/removed/changed paths (graph nodes keyed by id, e.g.
        `/pipeline/nodes/parse/config/max_pages`) with before/after values, secrets masked."""
        diff = await sdk.config_versions.diff(collection_id, from_version, to_version)
        return diff.model_dump(mode="json")

    @mcp.tool()
    async def restore_config_version(
        collection_id: str, version: int, confirm: bool = False
    ) -> Any:
        """Restore a config version as a NEW version (history is never rewritten).

        Without `confirm=true` NOTHING is written: the tool returns the diff from the current head to
        `version` (what the restore would change) — review it, then call again with `confirm=true`.
        Current same-endpoint provider keys are kept; a provider whose endpoint moved since that
        version is refused (422 — re-enter its key with a collection PATCH). Write capability.
        """
        # 1. Unconfirmed → preview only: diff current head → the target version.
        if not confirm:
            head = (await sdk.config_versions.list(collection_id, limit=1)).items[0].version
            diff = await sdk.config_versions.diff(collection_id, head, version)
            return {
                "restored": False,
                "message": f"Dry run: restoring v{version} over the current v{head} would apply "
                f"these changes. Call again with confirm=true to restore.",
                "diff": diff.model_dump(mode="json"),
            }
        # 2. Confirmed → the restore writes a new version.
        result = await sdk.config_versions.restore(collection_id, version)
        return {"restored": True, **result.model_dump(mode="json")}
