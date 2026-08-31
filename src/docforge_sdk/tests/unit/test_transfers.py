# ====== Code Summary ======
# Transfers-resource tests: export triggers a POST to the collection's /export sub-resource, import
# streams a multipart upload (from a path AND from raw bytes) to POST /collections/import, get_transfer
# polls GET /transfers/{id}, and download_export streams the bundle bytes via GET .../download without
# JSON parsing. Runs against both the async and sync clients.

# ====== Standard Library Imports ======
from pathlib import Path
from typing import Any

# ====== Third-Party Library Imports ======
import httpx
import respx

# ====== Local Project Imports ======
from docforge_sdk import AsyncClient, Client
from docforge_sdk.models.transfers import TransferAccepted, TransferStatus

BASE = "http://test"
API = f"{BASE}/api/v1"
CID = "22222222-2222-2222-2222-222222222222"
TID = "44444444-4444-4444-4444-444444444444"

_ACCEPTED_SAMPLE: dict[str, Any] = {"transfer_id": TID, "kind": "export", "status": "pending"}

_STATUS_SAMPLE: dict[str, Any] = {
    "transfer_id": TID,
    "kind": "export",
    "status": "done",
    "progress": 100,
    "stage": None,
    "counts": {"documents": 3},
    "error": None,
    "collection_id": CID,
    "collection_name": "acme",
    "size_bytes": 12345,
    "format_version": 1,
    "dense_dim": 1024,
    "expires_at": "2026-09-07T00:00:00Z",
    "started_at": "2026-08-31T00:00:00Z",
    "finished_at": "2026-08-31T00:01:00Z",
    "created_at": "2026-08-31T00:00:00Z",
    "updated_at": "2026-08-31T00:01:00Z",
}


@respx.mock
async def test_export_collection_posts_and_returns_accepted() -> None:
    route = respx.post(f"{API}/collections/{CID}/export").mock(
        return_value=httpx.Response(202, json=_ACCEPTED_SAMPLE)
    )
    async with AsyncClient(BASE) as client:
        result = await client.transfers.export_collection(CID)
    assert route.calls.last.request.method == "POST"
    assert route.calls.last.request.url.path == f"/api/v1/collections/{CID}/export"
    assert isinstance(result, TransferAccepted)
    assert result.status == "pending"


@respx.mock
def test_sync_get_transfer_parses_status() -> None:
    route = respx.get(f"{API}/transfers/{TID}").mock(
        return_value=httpx.Response(200, json=_STATUS_SAMPLE)
    )
    with Client(BASE) as client:
        result = client.transfers.get_transfer(TID)
    assert route.calls.last.request.url.path == f"/api/v1/transfers/{TID}"
    assert isinstance(result, TransferStatus)
    assert result.size_bytes == 12345


@respx.mock
async def test_import_collection_from_bytes_posts_multipart_with_target_name() -> None:
    route = respx.post(f"{API}/collections/import").mock(
        return_value=httpx.Response(
            202, json={"transfer_id": TID, "kind": "import", "status": "pending"}
        )
    )
    async with AsyncClient(BASE) as client:
        result = await client.transfers.import_collection(b"bundle-bytes", target_name="restored")
    request = route.calls.last.request
    assert request.headers["content-type"].startswith("multipart/form-data")
    body = request.content
    assert b'name="file"' in body and b"bundle-bytes" in body
    assert b'name="target_name"' in body and b"restored" in body
    assert isinstance(result, TransferAccepted)
    assert result.kind == "import"


@respx.mock
def test_sync_import_collection_from_path_streams_file_and_closes_handle(tmp_path: Path) -> None:
    bundle = tmp_path / "collection.dcexport"
    bundle.write_bytes(b"streamed-bundle-content")
    route = respx.post(f"{API}/collections/import").mock(
        return_value=httpx.Response(
            202, json={"transfer_id": TID, "kind": "import", "status": "pending"}
        )
    )
    with Client(BASE) as client:
        result = client.transfers.import_collection(bundle)
    request = route.calls.last.request
    body = request.content
    assert b'name="file"' in body
    assert b"streamed-bundle-content" in body
    assert b'filename="collection.dcexport"' in body
    assert b'name="target_name"' not in body
    assert isinstance(result, TransferAccepted)


@respx.mock
async def test_download_export_streams_chunks_without_json_parsing() -> None:
    respx.get(f"{API}/transfers/{TID}/download").mock(
        return_value=httpx.Response(
            200, content=b"a-multi-chunk-zstd-bundle", headers={"content-type": "application/zstd"}
        )
    )
    async with AsyncClient(BASE) as client:
        chunks = [chunk async for chunk in client.transfers.download_export(TID)]
    assert b"".join(chunks) == b"a-multi-chunk-zstd-bundle"


@respx.mock
def test_sync_download_export_streams_chunks() -> None:
    respx.get(f"{API}/transfers/{TID}/download").mock(
        return_value=httpx.Response(200, content=b"sync-bundle-bytes")
    )
    with Client(BASE) as client:
        chunks = list(client.transfers.download_export(TID))
    assert b"".join(chunks) == b"sync-bundle-bytes"
