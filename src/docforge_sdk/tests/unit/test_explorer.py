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
