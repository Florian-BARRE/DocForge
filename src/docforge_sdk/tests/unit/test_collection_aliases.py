# ====== Code Summary ======
# Collection-alias resource tests: list() GETs /collection-aliases → list[CollectionAliasModel];
# set() PUTs {collection_id} to /collection-aliases/{name} → SetCollectionAliasResponse; delete()
# DELETEs it. Verb + path + body + typed round-trip on the async client, plus a sync smoke.

# ====== Standard Library Imports ======
import json

# ====== Third-Party Library Imports ======
import httpx
import respx

# ====== Local Project Imports ======
from docforge_sdk import AsyncClient, Client
from docforge_sdk.models.collection_aliases import (
    CollectionAliasModel,
    SetCollectionAliasResponse,
)

BASE = "http://test"
API = f"{BASE}/api/v1"
_ALIAS = {
    "name": "chatmop",
    "collection_id": "c-2",
    "collection_name": "chatmop-v2",
    "created_at": "2026-10-07T00:00:00Z",
    "updated_at": "2026-10-07T01:00:00Z",
}


@respx.mock
async def test_list_gets_every_alias() -> None:
    respx.get(f"{API}/collection-aliases").mock(return_value=httpx.Response(200, json=[_ALIAS]))
    async with AsyncClient(BASE) as client:
        result = await client.collection_aliases.list()
    assert isinstance(result[0], CollectionAliasModel) and result[0].name == "chatmop"


@respx.mock
async def test_set_puts_the_target_and_reports_the_previous_one() -> None:
    route = respx.put(f"{API}/collection-aliases/chatmop").mock(
        return_value=httpx.Response(
            200, json={**_ALIAS, "previous_collection_id": "c-1", "created": False}
        )
    )
    async with AsyncClient(BASE) as client:
        result = await client.collection_aliases.set("chatmop", "c-2")
    assert json.loads(route.calls.last.request.content) == {"collection_id": "c-2"}
    assert isinstance(result, SetCollectionAliasResponse)
    assert result.previous_collection_id == "c-1" and result.created is False


@respx.mock
def test_sync_delete() -> None:
    route = respx.delete(f"{API}/collection-aliases/chatmop").mock(return_value=httpx.Response(204))
    with Client(BASE) as client:
        assert client.collection_aliases.delete("chatmop") is None
    assert route.called
