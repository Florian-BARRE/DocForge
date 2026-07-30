# ====== Code Summary ======
# Blobs-resource tests: the fetch hits GET /blobs/{hash} and wraps the raw bytes + the server-declared
# media type into a typed BlobContent. Runs against both the async and sync clients.

# ====== Third-Party Library Imports ======
import httpx
import respx

# ====== Local Project Imports ======
from docforge_sdk import AsyncClient, Client
from docforge_sdk.models.blobs import BlobContent

BASE = "http://test"
API = f"{BASE}/api/v1"
HASH = "sha256-abc"


@respx.mock
async def test_get_returns_bytes_and_mime() -> None:
    route = respx.get(f"{API}/blobs/{HASH}").mock(
        return_value=httpx.Response(200, content=b"\x89PNG", headers={"content-type": "image/png"})
    )
    async with AsyncClient(BASE) as client:
        result = await client.blobs.get(HASH)
    assert route.calls.last.request.method == "GET"
    assert route.calls.last.request.url.path == f"/api/v1/blobs/{HASH}"
    assert isinstance(result, BlobContent)
    assert result.content == b"\x89PNG"
    assert result.mime_type == "image/png"


@respx.mock
def test_sync_get_returns_blob_content() -> None:
    respx.get(f"{API}/blobs/{HASH}").mock(
        return_value=httpx.Response(200, content=b"data", headers={"content-type": "application/pdf"})
    )
    with Client(BASE) as client:
        result = client.blobs.get(HASH)
    assert result.content == b"data"
    assert result.mime_type == "application/pdf"
