# ====== Code Summary ======
# MCP tools for collection aliases — a thin wrapper over sdk.collection_aliases: list, a CONFIRM-gated
# set (creating an alias writes directly; re-pointing an existing one without confirm=true only
# previews old→new, since a switch re-scopes every key bound to `alias:<name>`), and delete. An alias
# name works wherever a tool takes `collection_id`.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP, sdk: AsyncClient) -> None:
    """Register the collection-alias tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (AsyncClient): The DocForge API client.
    """

    @mcp.tool()
    async def list_collection_aliases() -> Any:
        """List collection aliases (stable names like "chatmop" → one collection): name, target
        collection id + name, last re-point time. An alias name works wherever a tool takes
        `collection_id`, so prefer it over a UUID that changes when a collection is rebuilt."""
        aliases = await sdk.collection_aliases.list()
        return [alias.model_dump(mode="json") for alias in aliases]

    @mcp.tool()
    async def set_collection_alias(name: str, collection_id: str, confirm: bool = False) -> Any:
        """Create an alias, or re-point ("switch") an existing one to another collection.

        `name` is a slug (lowercase, digits, '-', '_'); `collection_id` is the target UUID. Creating
        a new alias writes immediately. Re-pointing an existing alias moves every key scoped
        `alias:<name>` and every client using the name: without `confirm=true` NOTHING is written and
        the tool returns the old → new target — review, then call again with `confirm=true`.
        Requires a FULL-ACCESS admin key (a collection-scoped key is refused: an alias re-scopes
        every key bound to it).
        """
        # 1. Preview a re-point (an existing alias moving elsewhere) unless confirmed.
        current = {alias.name: alias for alias in await sdk.collection_aliases.list()}.get(name)
        if current is not None and current.collection_id != collection_id and not confirm:
            return {
                "applied": False,
                "message": f"Dry run: alias '{name}' would move from {current.collection_id} "
                f"({current.collection_name}) to {collection_id}. Call again with confirm=true.",
                "from_collection_id": current.collection_id,
                "to_collection_id": collection_id,
            }
        # 2. Create, or the confirmed switch.
        result = await sdk.collection_aliases.set(name, collection_id)
        return {"applied": True, **result.model_dump(mode="json")}

    @mcp.tool()
    async def delete_collection_alias(name: str) -> Any:
        """Delete a collection alias (the collection itself is untouched). Requires a FULL-ACCESS
        admin key; refused (409) while live keys are still scoped `alias:<name>` -- re-scope or
        revoke them first, or re-point the alias instead."""
        await sdk.collection_aliases.delete(name)
        return {"deleted": True, "name": name}
