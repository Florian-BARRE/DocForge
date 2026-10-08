# ====== Code Summary ======
# MCP tools for the pipelines domain — thin wrappers over sdk.pipelines: discovery + the lean
# palette/blob payload (read-only) plus the design-editing surface (inspect / edit / stage view /
# stage apply). The graph JSON stays OPAQUE at the tool boundary — blob/operations/action pass
# through as plain dicts exactly as the LLM supplies them.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP, sdk: AsyncClient) -> None:
    """Register pipeline design tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (AsyncClient): The DocForge API client.
    """

    @mcp.tool()
    async def list_pipeline_surfaces() -> Any:
        """Discover the available pipeline design surfaces (ingest / search) and their URLs."""
        result = await sdk.pipelines.list_surfaces()
        return result.model_dump(mode="json")

    @mcp.tool()
    async def get_pipeline_design(key: str, full: bool = False) -> Any:
        """
        Open a pipeline design surface: the block palette, the default blob, the curated
        creation `presets` (each with a name + label + rationale — the name is what you pass as
        create_collection's `preset` / `search_preset`), and any validation issues. `key` is
        "ingest" or "search"; `full=true` adds the advanced palette blocks (run_inputs, mechanics,
        artefacts). `mechanics` is self-describing:
        its `edit_operations` / `stage_actions` cards give the tag + params_schema of every
        `edit`/`stages.apply` payload variant, so compose those from it rather than guessing.
        """
        result = await sdk.pipelines.get_design(key, full=full)
        return result.model_dump(mode="json")

    @mcp.tool()
    async def inspect_pipeline(key: str, blob: dict[str, Any]) -> Any:
        """
        Inspect an edited pipeline blob without saving it: validity, every issue found, and
        the described tree of the graph (or a build_error when it cannot even be built).
        """
        result = await sdk.pipelines.inspect(key, blob)
        return result.model_dump(mode="json")

    @mcp.tool()
    async def edit_pipeline(
        key: str, blob: dict[str, Any], operations: list[dict[str, Any]]
    ) -> Any:
        """
        Apply ordered graph operations to a pipeline blob, server-side, then build + validate
        + describe the result. Returns the edited blob (or the original one when an operation
        was impossible) plus its validity, issues, described tree and edit_error.

        Each operation is ``{<discriminator>: <kind>, **params}``; get the discriminator key and
        every kind + params_schema from ``palette.mechanics.edit_operations`` (GET a pipeline with
        ``full=true``) — the ``discriminator`` field on each card names the tag key to send under.
        """
        result = await sdk.pipelines.edit(key, blob, operations)
        return result.model_dump(mode="json")

    @mcp.tool()
    async def view_pipeline_stages(key: str, blob: dict[str, Any]) -> Any:
        """Derive the ordered stage view of a pipeline blob plus its validity verdict."""
        result = await sdk.pipelines.view_stages(key, blob)
        return result.model_dump(mode="json")

    @mcp.tool()
    async def apply_pipeline_stage(key: str, blob: dict[str, Any], action: dict[str, Any]) -> Any:
        """
        Compile a stage-level action into a pipeline blob you hold — STATELESS, nothing is saved.
        Returns the recompiled blob (always buildable), its stage view, validity, issues and any
        compiler notices. To change an EXISTING collection's pipeline, use apply_collection_stage
        instead: it applies the action to the stored pipeline and persists it, so you never
        round-trip the full blob (whose secrets come back masked) through update_collection.

        The action is ``{<discriminator>: <kind>, **params}``; get the discriminator key and every
        kind + params_schema from ``palette.mechanics.stage_actions`` (GET a pipeline with
        ``full=true``) — the ``discriminator`` field on each card names the tag key to send under.
        """
        result = await sdk.pipelines.apply_stage(key, blob, action)
        return result.model_dump(mode="json")

    @mcp.tool()
    async def apply_collection_stage(
        collection_id: str, action: dict[str, Any], note: str | None = None
    ) -> Any:
        """
        Apply ONE stage action to a collection's stored ingestion pipeline and save it — the safe
        way to edit a collection's pipeline (no full-blob round-trip). Returns the stage view
        (secrets masked), validity, issues, notices and `persisted`: nothing is saved when the
        result is invalid or the action changed nothing (read the notices).

        `action` is ``{"action": <kind>, **params}`` (kinds + params_schema in
        ``palette.mechanics.stage_actions``). A ``set_config`` defaults to ``mode="merge"`` here:
        only the keys you send change, every other key — the api_key included — is kept; send a
        key as null to reset it to its default. Pass ``mode="replace"`` explicitly to replace the
        whole config. An omitted api_key is always kept; an explicit "" clears it.

        The embed stage has two independent provider slots, ``dense`` and ``sparse`` (listed in the
        stage view's ``slots`` with each slot's ``provider``, ``available`` kinds and
        ``config_schemas``). Set a slot provider with
        ``{"action": "set_provider", "stage": "embed", "slot": "sparse", "kind": "bm25_local"}``
        (dense kinds: bge_server, openai_compatible; sparse kinds: bge_server, bm25_local). Turn a
        slot off with ``"kind": null`` (refused if the other slot is already off). Edit one slot's
        config with ``{"action": "set_config", "stage": "embed", "slot": "dense",
        "config": {"base_url": "...", "api_key": "..."}}``. Changing a provider sets
        ``needs_reindex``: then run rebuild_index (or reingest when a dense slot was added).
        """
        payload = dict(action)
        if payload.get("action") == "set_config":
            payload.setdefault("mode", "merge")
        result = await sdk.pipelines.apply_collection_stage(collection_id, payload, note=note)
        return result.model_dump(mode="json")
