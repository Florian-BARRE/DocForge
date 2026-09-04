# ====== Code Summary ======
# Snippets-resource tests: granular collection-config export/apply. export() GETs
# /collections/{id}/snippets/{kind} → CollectionSnippet; apply() POSTs the snippet body to the same
# sub-resource → SnippetImportResult. Verb + path + typed round-trip on the async client, plus a sync smoke.

# ====== Third-Party Library Imports ======
import httpx
import respx

# ====== Local Project Imports ======
from docforge_sdk import AsyncClient, Client
from docforge_sdk.models.snippets import CollectionSnippet, SnippetImportResult

BASE = "http://test"
API = f"{BASE}/api/v1"
CID = "col-1"
_SNIPPET = {
    "kind": "pipeline",
    "format_version": 1,
    "docforge_version": "0.14.3",
    "body": {"nodes": [], "edges": []},
}
_IMPORT_RESULT = {"collection_id": CID, "kind": "pipeline", "needs_reindex": False}


@respx.mock
async def test_export_gets_the_kind_sub_resource() -> None:
    route = respx.get(f"{API}/collections/{CID}/snippets/pipeline").mock(
        return_value=httpx.Response(200, json=_SNIPPET)
    )
    async with AsyncClient(BASE, api_token="t") as client:
        result = await client.snippets.export(CID, "pipeline")
    request = route.calls.last.request
    assert request.method == "GET"
    assert request.url.path == f"/api/v1/collections/{CID}/snippets/pipeline"
    assert isinstance(result, CollectionSnippet)
    assert result.kind == "pipeline"


@respx.mock
async def test_apply_posts_the_snippet_body() -> None:
    route = respx.post(f"{API}/collections/{CID}/snippets/pipeline").mock(
        return_value=httpx.Response(200, json=_IMPORT_RESULT)
    )
    snippet = CollectionSnippet.model_validate(_SNIPPET)
    async with AsyncClient(BASE, api_token="t") as client:
        result = await client.snippets.apply(CID, "pipeline", snippet)
    request = route.calls.last.request
    assert request.method == "POST"
    assert request.url.path == f"/api/v1/collections/{CID}/snippets/pipeline"
    assert isinstance(result, SnippetImportResult)


@respx.mock
def test_sync_export_gets_the_kind_sub_resource() -> None:
    route = respx.get(f"{API}/collections/{CID}/snippets/search").mock(
        return_value=httpx.Response(200, json={**_SNIPPET, "kind": "search"})
    )
    with Client(BASE) as client:
        result = client.snippets.export(CID, "search")
    assert route.calls.last.request.url.path == f"/api/v1/collections/{CID}/snippets/search"
    assert isinstance(result, CollectionSnippet)
