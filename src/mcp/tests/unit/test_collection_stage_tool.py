# ====== Code Summary ======
# Wave E (safe admin): apply_collection_stage forwards ONE stage action to the collection-scoped route,
# defaulting a set_config to mode="merge" (an explicit mode wins, other actions pass through untouched).

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any
from unittest.mock import AsyncMock

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from docforge_sdk.models import CollectionStageApplyResponse

# ====== Internal Project Imports ======
from libs.server import build_mcp

CID = "11111111-1111-1111-1111-111111111111"


def _wired() -> tuple[Any, AsyncMock]:
    sdk = AsyncClient("http://localhost:8000")
    apply = AsyncMock(
        return_value=CollectionStageApplyResponse(
            collection_id=CID, persisted=True, stages=[], valid=True
        )
    )
    sdk.pipelines.apply_collection_stage = apply  # type: ignore[method-assign]
    return build_mcp(sdk), apply


async def test_set_config_defaults_to_merge() -> None:
    mcp, apply = _wired()
    action = {"action": "set_config", "stage": "embed", "config": {"timeout_seconds": 30}}
    await mcp.call_tool("apply_collection_stage", {"collection_id": CID, "action": action})
    assert apply.call_args.args == (CID, {**action, "mode": "merge"})
    assert apply.call_args.kwargs == {"note": None}


async def test_explicit_replace_and_other_actions_pass_through() -> None:
    mcp, apply = _wired()
    replace = {"action": "set_config", "stage": "embed", "config": {}, "mode": "replace"}
    await mcp.call_tool("apply_collection_stage", {"collection_id": CID, "action": replace})
    assert apply.call_args.args[1]["mode"] == "replace"
    toggle = {"action": "enable_stage", "stage": "enrich"}
    await mcp.call_tool(
        "apply_collection_stage", {"collection_id": CID, "action": toggle, "note": "n"}
    )
    assert apply.call_args.args[1] == toggle
    assert apply.call_args.kwargs == {"note": "n"}
