# ====== Code Summary ======
# Search-resource test: the query hits POST /collections/{id}/search carrying the serialised request
# body and returns a typed SearchResponse. Runs against both the async and sync clients.

# ====== Standard Library Imports ======
import json
from typing import Any

# ====== Third-Party Library Imports ======
import httpx
import respx

# ====== Local Project Imports ======
from docforge_sdk import AsyncClient, Client
from docforge_sdk.models.search import SearchRequest, SearchResponse

BASE = "http://test"
API = f"{BASE}/api/v1"
CID = "22222222-2222-2222-2222-222222222222"

_RESPONSE_SAMPLE: dict[str, Any] = {
    "query": "hello",
    "hits": [
        {
            "chunk_id": "c1",
            "document_id": "d1",
            "score": 0.9,
            "text": "hello world",
            "chunk_index": 0,
            "token_count": 2,
        }
    ],
    "debug_info": None,
}


@respx.mock
async def test_search_posts_query_and_returns_response() -> None:
    route = respx.post(f"{API}/collections/{CID}/search").mock(
        return_value=httpx.Response(200, json=_RESPONSE_SAMPLE)
    )
    async with AsyncClient(BASE) as client:
        result = await client.search.search(CID, SearchRequest(query="hello", limit=5))
    assert route.calls.last.request.method == "POST"
    assert route.calls.last.request.url.path == f"/api/v1/collections/{CID}/search"
    body = json.loads(route.calls.last.request.content)
    assert body["query"] == "hello" and body["limit"] == 5
    assert isinstance(result, SearchResponse)
    assert result.hits[0].chunk_id == "c1"


@respx.mock
def test_sync_search_returns_response() -> None:
    respx.post(f"{API}/collections/{CID}/search").mock(
        return_value=httpx.Response(200, json=_RESPONSE_SAMPLE)
    )
    with Client(BASE) as client:
        result = client.search.search(CID, SearchRequest(query="hello"))
    assert isinstance(result, SearchResponse)
