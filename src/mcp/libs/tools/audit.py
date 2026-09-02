# ====== Code Summary ======
# MCP tools for the audit domain — a thin wrapper over sdk.audit (ROOT/full-access only).

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP, sdk: AsyncClient) -> None:
    """Register audit tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (AsyncClient): The DocForge API client.
    """

    @mcp.tool()
    async def list_audit(
        limit: int | None = None,
        cursor: str | None = None,
        actor_user_id: str | None = None,
        actor_key_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        correlation_id: str | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
    ) -> Any:
        """List one keyset-paginated page of the audit trail, newest first (ROOT/full-access only).

        Records one row per mutating API action (who/what/target/outcome). The page is bounded
        server-side; pass ``cursor`` (a previous page's ``next_cursor``) to walk the trail. Filter by
        actor (``actor_user_id``/``actor_key_id``), target (``target_type``+``target_id``),
        ``correlation_id``, and an ISO-8601 event-time window (``created_from``/``created_to``). A
        collection-scoped key is rejected 403.
        """
        from datetime import datetime  # noqa: PLC0415 — parse ISO bounds only when supplied

        page = await sdk.audit.list(
            limit=limit,
            cursor=cursor,
            actor_user_id=actor_user_id,
            actor_key_id=actor_key_id,
            target_type=target_type,
            target_id=target_id,
            correlation_id=correlation_id,
            created_from=datetime.fromisoformat(created_from) if created_from else None,
            created_to=datetime.fromisoformat(created_to) if created_to else None,
        )
        return page.model_dump(mode="json")
