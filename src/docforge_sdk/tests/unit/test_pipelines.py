# ====== Code Summary ======
# Pipelines-resource tests: discovery returns a typed PipelineIndexResponse, and the advanced
# inspect/edit round-trips prove the OPAQUE graph payloads (blob / operations) pass through untouched
# while only the typed ENVELOPE is parsed back. Runs against both the async and sync clients.

# ====== Standard Library Imports ======
import json
from typing import Any

# ====== Third-Party Library Imports ======
import httpx
import respx

# ====== Local Project Imports ======
from docforge_sdk import AsyncClient, Client
from docforge_sdk.models.pipelines import (
    EditResponse,
    InspectResponse,
    PipelineIndexResponse,
)

BASE = "http://test"
API = f"{BASE}/api/v1"
KEY = "ingest"

_BLOB: dict[str, Any] = {"kind": "group", "nodes": [{"id": "n1", "kind": "intake"}], "opaque": True}
_OPERATIONS: list[dict[str, Any]] = [{"op": "add_node", "kind": "parser", "payload": {"deep": [1, 2]}}]


@respx.mock
async def test_list_surfaces_returns_index() -> None:
    route = respx.get(f"{API}/pipelines").mock(
        return_value=httpx.Response(200, json={"pipelines": []})
    )
    async with AsyncClient(BASE) as client:
        result = await client.pipelines.list_surfaces()
    assert route.calls.last.request.method == "GET"
    assert isinstance(result, PipelineIndexResponse)


@respx.mock
async def test_inspect_roundtrips_opaque_blob() -> None:
    route = respx.post(f"{API}/pipelines/{KEY}/inspect").mock(
        return_value=httpx.Response(200, json={"valid": True, "issues": [], "explored": {"a": 1}})
    )
    async with AsyncClient(BASE) as client:
        result = await client.pipelines.inspect(KEY, _BLOB)
    assert route.calls.last.request.url.path == f"/api/v1/pipelines/{KEY}/inspect"
    # The opaque blob must pass through the wire byte-for-byte (no reshaping in the SDK).
    assert json.loads(route.calls.last.request.content) == {"blob": _BLOB}
    assert isinstance(result, InspectResponse)
    assert result.valid is True
    assert result.explored == {"a": 1}


@respx.mock
def test_sync_edit_roundtrips_opaque_operations() -> None:
    route = respx.post(f"{API}/pipelines/{KEY}/edit").mock(
        return_value=httpx.Response(200, json={"blob": _BLOB, "valid": False, "issues": [{"code": "x"}]})
    )
    with Client(BASE) as client:
        result = client.pipelines.edit(KEY, _BLOB, _OPERATIONS)
    assert json.loads(route.calls.last.request.content) == {"blob": _BLOB, "operations": _OPERATIONS}
    assert isinstance(result, EditResponse)
    # The opaque envelope fields round-trip untouched.
    assert result.blob == _BLOB
    assert result.issues == [{"code": "x"}]
