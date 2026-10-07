# ====== Code Summary ======
# Explorer-resource tests (including the IR view): the browse list, the full-IR read and the bulk
# chunk toggle each hit the exact URL + method and return the correctly typed model. Runs against both
# the async and sync clients.

# ====== Standard Library Imports ======
import json
from typing import Any

# ====== Third-Party Library Imports ======
import httpx
import respx

# ====== Local Project Imports ======
from docforge_sdk import AsyncClient, Client
from docforge_sdk.models.explorer import (
    BulkChunkEnabledPatch,
    BulkChunkEnabledResponse,
    DocumentListItem,
)
from docforge_sdk.models.ir import DocumentIRModel

BASE = "http://test"
API = f"{BASE}/api/v1"
CID = "22222222-2222-2222-2222-222222222222"
DID = "33333333-3333-3333-3333-333333333333"
CHUNK = "44444444-4444-4444-4444-444444444444"

_LIST_ITEM: dict[str, Any] = {
    "id": DID,
    "filename": "a.pdf",
    "format": "pdf",
    "status": "done",
    "page_count": 3,
    "file_size": 10,
    "created_at": "2026-01-01T00:00:00Z",
    "title": "A",
    "language": "en",
    "enabled": True,
}
_IR_SAMPLE: dict[str, Any] = {
    "blocks": [
        {
            "id": "b1",
            "block_type": "text",
            "page": 0,
            "page_number": 1,
            "bbox": [0.0, 0.0, 1.0, 1.0],
            "reading_order": 0,
            "column_index": 0,
            "text": "hi",
            "is_boilerplate": False,
        }
    ],
    "tables": [],
    "figures": [],
    "enrichments": [{"id": "e1", "block_id": "b1", "kind": "ocr", "text": "hi", "status": "ok"}],
}


@respx.mock
async def test_list_documents_returns_typed_list() -> None:
    route = respx.get(f"{API}/collections/{CID}/documents").mock(
        return_value=httpx.Response(200, json=[_LIST_ITEM])
    )
    async with AsyncClient(BASE) as client:
        result = await client.explorer.list_documents(CID)
    assert route.calls.last.request.method == "GET"
    assert route.calls.last.request.url.path == f"/api/v1/collections/{CID}/documents"
    assert len(result) == 1 and isinstance(result[0], DocumentListItem)


@respx.mock
async def test_get_ir_returns_document_ir() -> None:
    route = respx.get(f"{API}/documents/{DID}/ir").mock(
        return_value=httpx.Response(200, json=_IR_SAMPLE)
    )
    async with AsyncClient(BASE) as client:
        result = await client.explorer.get_ir(DID)
    assert route.calls.last.request.url.path == f"/api/v1/documents/{DID}/ir"
    assert isinstance(result, DocumentIRModel)
    assert result.blocks[0].id == "b1"
    assert result.enrichments[0].kind == "ocr"


@respx.mock
def test_sync_set_chunks_enabled_posts_body_and_returns_response() -> None:
    route = respx.patch(f"{API}/chunks/enabled").mock(
        return_value=httpx.Response(200, json={"results": [], "not_found": []})
    )
    with Client(BASE) as client:
        result = client.explorer.set_chunks_enabled(
            BulkChunkEnabledPatch(chunk_ids=[CHUNK], enabled=True)
        )
    assert route.calls.last.request.method == "PATCH"
    assert json.loads(route.calls.last.request.content) == {"chunk_ids": [CHUNK], "enabled": True}
    assert isinstance(result, BulkChunkEnabledResponse)


_LEAN_CHUNK: dict[str, Any] = {
    "id": CHUNK,
    "chunk_index": 0,
    "text": "t",
    "token_count": 1,
    "is_indexed": True,
    "role": "body",
    "enabled": True,
    "strategy": "recursive",
}


@respx.mock
async def test_get_chunks_sends_no_query_when_nothing_set() -> None:
    route = respx.get(f"{API}/documents/{DID}/chunks").mock(
        return_value=httpx.Response(200, json=[_LEAN_CHUNK])
    )
    async with AsyncClient(BASE) as client:
        result = await client.explorer.get_chunks(DID)
    assert route.calls.last.request.url.query == b""
    # A lean (geometry-less) item parses: block_ids/page are absent from the wire.
    assert result[0].block_ids == [] and result[0].page is None


@respx.mock
async def test_get_chunks_page_forwards_set_params_and_reads_total() -> None:
    route = respx.get(f"{API}/documents/{DID}/chunks").mock(
        return_value=httpx.Response(200, json=[_LEAN_CHUNK], headers={"X-Total-Count": "42"})
    )
    with Client(BASE) as client:
        page = client.explorer.get_chunks_page(DID, limit=20, offset=0, include_geometry=False)
    query = route.calls.last.request.url.params
    assert dict(query) == {"limit": "20", "offset": "0", "include_geometry": "false"}
    assert page.total == 42 and len(page.items) == 1


@respx.mock
async def test_get_chunks_page_total_none_without_header() -> None:
    respx.get(f"{API}/documents/{DID}/chunks").mock(return_value=httpx.Response(200, json=[]))
    async with AsyncClient(BASE) as client:
        page = await client.explorer.get_chunks_page(DID)
    assert page.total is None and page.items == []


@respx.mock
async def test_list_documents_forwards_paging_only_when_set() -> None:
    route = respx.get(f"{API}/collections/{CID}/documents").mock(
        return_value=httpx.Response(200, json=[])
    )
    async with AsyncClient(BASE) as client:
        await client.explorer.list_documents(CID)
        assert route.calls.last.request.url.query == b""
        await client.explorer.list_documents(CID, limit=5, offset=10)
    assert dict(route.calls.last.request.url.params) == {"limit": "5", "offset": "10"}


@respx.mock
async def test_get_outline_and_chunk_context_typed() -> None:
    respx.get(f"{API}/documents/{DID}/outline").mock(
        return_value=httpx.Response(
            200,
            json={
                "document_id": DID,
                "display_title": "T",
                "page_count": 3,
                "headings": [{"level": 1, "text": "Intro", "page_number": 1, "chunk_id": CHUNK}],
            },
        )
    )
    ctx_route = respx.get(f"{API}/chunks/{CHUNK}/context").mock(
        return_value=httpx.Response(
            200,
            json={
                "document_id": DID,
                "display_title": "T",
                "chunks": [
                    {
                        "chunk_id": CHUNK,
                        "chunk_index": 0,
                        "text": "x",
                        "token_count": 1,
                        "is_target": True,
                    }
                ],
            },
        )
    )
    async with AsyncClient(BASE) as client:
        outline = await client.explorer.get_outline(DID)
        assert outline.headings[0].chunk_id == CHUNK and outline.page_count == 3
        context = await client.explorer.get_chunk_context(CHUNK)
        assert ctx_route.calls.last.request.url.query == b""
        await client.explorer.get_chunk_context(CHUNK, before=2, after=0)
    assert context.chunks[0].is_target
    assert dict(ctx_route.calls.last.request.url.params) == {"before": "2", "after": "0"}
