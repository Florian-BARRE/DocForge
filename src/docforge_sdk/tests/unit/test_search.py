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
from docforge_sdk.models.search import ChunkBrowseRequest, SearchRequest, SearchResponse

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


@respx.mock
async def test_search_default_body_omits_max_per_document() -> None:
    route = respx.post(f"{API}/collections/{CID}/search").mock(
        return_value=httpx.Response(200, json=_RESPONSE_SAMPLE)
    )
    async with AsyncClient(BASE) as client:
        await client.search.search(CID, SearchRequest(query="hello"))
    body = json.loads(route.calls.last.request.content)
    # The backend 422s an orphan max_per_document, so the untouched default must not be sent; and
    # unused shaping knobs are omitted entirely so a pre-0.24 server (extra="forbid") still accepts
    # a plain search.
    assert "max_per_document" not in body
    assert "return_fields" not in body
    assert "group_by" not in body
    for knob in ("min_score", "rerank", "fusion", "debug"):
        assert knob not in body


@respx.mock
async def test_search_forwards_projection_and_grouping() -> None:
    route = respx.post(f"{API}/collections/{CID}/search").mock(
        return_value=httpx.Response(
            200,
            json={"query": "q", "hits": [{"chunk_id": "c1", "document_id": "d1", "text": "t"}]},
        )
    )
    request = SearchRequest(
        query="q", return_fields=["text", "metadata.topic"], group_by="document", max_per_document=2
    )
    async with AsyncClient(BASE) as client:
        result = await client.search.search(CID, request)
    body = json.loads(route.calls.last.request.content)
    assert body["return_fields"] == ["text", "metadata.topic"]
    assert body["group_by"] == "document" and body["max_per_document"] == 2
    # A projected hit carries only identity + requested keys; the rest stay unset.
    assert result.hits[0].model_fields_set == {"chunk_id", "document_id", "text"}


@respx.mock
def test_sync_search_explicit_orphan_max_per_document_is_sent() -> None:
    route = respx.post(f"{API}/collections/{CID}/search").mock(
        return_value=httpx.Response(200, json=_RESPONSE_SAMPLE)
    )
    with Client(BASE) as client:
        client.search.search(CID, SearchRequest(query="q", max_per_document=3))
    assert json.loads(route.calls.last.request.content)["max_per_document"] == 3


@respx.mock
async def test_search_forwards_wave_c_knobs_when_set() -> None:
    route = respx.post(f"{API}/collections/{CID}/search").mock(
        return_value=httpx.Response(200, json=_RESPONSE_SAMPLE)
    )
    request = SearchRequest(
        query="q", min_score=0.3, rerank=False, fusion="dbsf", debug=True, filters={"k": {"not": 1}}
    )
    async with AsyncClient(BASE) as client:
        await client.search.search(CID, request)
    body = json.loads(route.calls.last.request.content)
    assert (body["min_score"], body["rerank"], body["fusion"], body["debug"]) == (
        0.3,
        False,
        "dbsf",
        True,
    )
    assert body["filters"] == {"k": {"not": 1}}


@respx.mock
async def test_browse_posts_and_parses_cursor() -> None:
    route = respx.post(f"{API}/collections/{CID}/chunks/browse").mock(
        return_value=httpx.Response(
            200,
            json={
                "chunks": [{"chunk_id": "c1", "document_id": "d1", "text": "t"}],
                "next_cursor": "abc",
                "hints": [],
            },
        )
    )
    async with AsyncClient(BASE) as client:
        page = await client.search.browse(CID, ChunkBrowseRequest(filters={"a": "b"}, limit=5))
    assert json.loads(route.calls.last.request.content) == {"filters": {"a": "b"}, "limit": 5}
    assert page.next_cursor == "abc" and page.chunks[0].chunk_id == "c1"


@respx.mock
def test_sync_browse_sends_cursor() -> None:
    route = respx.post(f"{API}/collections/{CID}/chunks/browse").mock(
        return_value=httpx.Response(200, json={"chunks": [], "next_cursor": None, "hints": []})
    )
    with Client(BASE) as client:
        page = client.search.browse(CID, ChunkBrowseRequest(cursor="abc"))
    assert json.loads(route.calls.last.request.content)["cursor"] == "abc"
    assert page.next_cursor is None
