# ====== Code Summary ======
# Corpus-resource tests: the server-side document grid. query() POSTs a filter/sort/pagination body to
# /collections/{id}/documents/query; bulk_reingest() POSTs a selector to .../documents/reingest with a
# ``force`` query param. Each is checked on the async client (verb + path + body), plus a sync smoke.

# ====== Third-Party Library Imports ======
import httpx
import respx

# ====== Local Project Imports ======
from docforge_sdk import AsyncClient, Client
from docforge_sdk.models.corpus import (
    BulkReingestResponse,
    DocumentQueryRequest,
    DocumentQueryResponse,
    DocumentSelector,
)

BASE = "http://test"
API = f"{BASE}/api/v1"
CID = "col-1"
_QUERY_RESPONSE = {"total": 0, "limit": 50, "offset": 0, "rows": []}
_REINGEST_RESPONSE = {
    "collection_id": CID,
    "matched": 2,
    "enqueued": 2,
    "capped": False,
    "max_fanout": 100,
    "jobs": [],
}


@respx.mock
async def test_query_posts_to_documents_query() -> None:
    route = respx.post(f"{API}/collections/{CID}/documents/query").mock(
        return_value=httpx.Response(200, json=_QUERY_RESPONSE)
    )
    async with AsyncClient(BASE, api_token="t") as client:
        result = await client.corpus.query(CID, DocumentQueryRequest())
    request = route.calls.last.request
    assert request.method == "POST"
    assert request.url.path == f"/api/v1/collections/{CID}/documents/query"
    assert isinstance(result, DocumentQueryResponse)


@respx.mock
async def test_bulk_reingest_posts_selector_with_force_param() -> None:
    route = respx.post(f"{API}/collections/{CID}/documents/reingest").mock(
        return_value=httpx.Response(200, json=_REINGEST_RESPONSE)
    )
    async with AsyncClient(BASE, api_token="t") as client:
        result = await client.corpus.bulk_reingest(
            CID, DocumentSelector(document_ids=["d1", "d2"]), force=True
        )
    request = route.calls.last.request
    assert request.method == "POST"
    assert request.url.path == f"/api/v1/collections/{CID}/documents/reingest"
    assert request.url.params["force"] == "true"
    assert isinstance(result, BulkReingestResponse)


@respx.mock
def test_sync_query_posts_to_documents_query() -> None:
    route = respx.post(f"{API}/collections/{CID}/documents/query").mock(
        return_value=httpx.Response(200, json=_QUERY_RESPONSE)
    )
    with Client(BASE) as client:
        result = client.corpus.query(CID)
    assert route.calls.last.request.url.path == f"/api/v1/collections/{CID}/documents/query"
    assert isinstance(result, DocumentQueryResponse)
