# ====== Code Summary ======
# Documents-resource tests: the multipart upload hits POST /documents (carrying the file part + the
# collection_id/metadata form fields) and returns UploadAccepted; the toggle hits the /enabled PATCH.
# Runs against both the async and sync clients.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
import httpx
import respx

# ====== Local Project Imports ======
from docforge_sdk import AsyncClient, Client
from docforge_sdk.models.documents import DocumentEnabledResponse, UploadAccepted

BASE = "http://test"
API = f"{BASE}/api/v1"
CID = "22222222-2222-2222-2222-222222222222"
DID = "33333333-3333-3333-3333-333333333333"

_ACCEPTED_SAMPLE: dict[str, Any] = {"document_id": DID, "job_id": "job-1", "duplicate": False}


@respx.mock
async def test_upload_posts_multipart_and_returns_accepted() -> None:
    route = respx.post(f"{API}/documents").mock(
        return_value=httpx.Response(202, json=_ACCEPTED_SAMPLE)
    )
    async with AsyncClient(BASE) as client:
        result = await client.documents.upload(CID, b"hello", {"lang": "en"}, filename="a.txt")
    request = route.calls.last.request
    assert request.method == "POST"
    assert request.url.path == "/api/v1/documents"
    assert request.headers["content-type"].startswith("multipart/form-data")
    body = request.content
    assert b'name="collection_id"' in body and CID.encode() in body
    assert b'name="metadata"' in body and b'"lang": "en"' in body
    assert b'name="file"' in body and b"hello" in body
    assert isinstance(result, UploadAccepted)


@respx.mock
def test_sync_set_enabled_patches_and_returns_state() -> None:
    route = respx.patch(f"{API}/documents/{DID}/enabled").mock(
        return_value=httpx.Response(200, json={"document_id": DID, "enabled": False})
    )
    with Client(BASE) as client:
        result = client.documents.set_enabled(DID, enabled=False)
    assert route.calls.last.request.method == "PATCH"
    assert route.calls.last.request.url.path == f"/api/v1/documents/{DID}/enabled"
    assert isinstance(result, DocumentEnabledResponse)
    assert result.enabled is False
