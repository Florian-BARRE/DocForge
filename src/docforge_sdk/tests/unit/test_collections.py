# ====== Code Summary ======
# Collections-resource tests: each method hits the exact URL + HTTP method and returns the correctly
# typed model (list[CollectionModel] for the list). Runs against both the async and sync clients.

# ====== Standard Library Imports ======
import json
from typing import Any

# ====== Third-Party Library Imports ======
import httpx
import respx

# ====== Local Project Imports ======
from docforge_sdk import AsyncClient, Client
from docforge_sdk.models.collections import (
    CollectionModel,
    CreateCollectionRequest,
    UpdateCollectionRequest,
)

BASE = "http://test"
API = f"{BASE}/api/v1"
CID = "22222222-2222-2222-2222-222222222222"

_COLLECTION_SAMPLE: dict[str, Any] = {
    "id": CID,
    "name": "docs",
    "supported_formats": ["pdf"],
    "max_file_size_bytes": 1000,
    "needs_reindex": False,
    "created_at": "2026-01-01T00:00:00Z",
    "pipeline": {"nodes": []},
    "search": {},
    "fields": [],
}


@respx.mock
async def test_list_returns_typed_list() -> None:
    route = respx.get(f"{API}/collections").mock(
        return_value=httpx.Response(200, json=[_COLLECTION_SAMPLE])
    )
    async with AsyncClient(BASE) as client:
        result = await client.collections.list()
    assert route.calls.last.request.method == "GET"
    assert len(result) == 1 and isinstance(result[0], CollectionModel)


@respx.mock
async def test_get_returns_collection() -> None:
    route = respx.get(f"{API}/collections/{CID}").mock(
        return_value=httpx.Response(200, json=_COLLECTION_SAMPLE)
    )
    async with AsyncClient(BASE) as client:
        result = await client.collections.get(CID)
    assert route.calls.last.request.url.path == f"/api/v1/collections/{CID}"
    assert isinstance(result, CollectionModel)


@respx.mock
async def test_create_posts_and_returns_collection() -> None:
    route = respx.post(f"{API}/collections").mock(
        return_value=httpx.Response(201, json=_COLLECTION_SAMPLE)
    )
    request = CreateCollectionRequest(
        name="docs", supported_formats=["pdf"], max_file_size_bytes=1000
    )
    async with AsyncClient(BASE) as client:
        result = await client.collections.create(request)
    assert route.calls.last.request.method == "POST"
    assert isinstance(result, CollectionModel)


@respx.mock
async def test_update_patches_only_set_fields() -> None:
    route = respx.patch(f"{API}/collections/{CID}").mock(
        return_value=httpx.Response(200, json=_COLLECTION_SAMPLE)
    )
    async with AsyncClient(BASE) as client:
        await client.collections.update(CID, UpdateCollectionRequest(name="renamed"))
    body = json.loads(route.calls.last.request.content)
    assert body == {"name": "renamed"}


@respx.mock
def test_sync_delete_returns_none() -> None:
    route = respx.delete(f"{API}/collections/{CID}").mock(return_value=httpx.Response(204))
    with Client(BASE) as client:
        result = client.collections.delete(CID)
    assert route.calls.last.request.method == "DELETE"
    assert result is None


_S3_FOOTPRINT_SAMPLE: dict[str, Any] = {
    "original_bytes": 1000,
    "rendered_bytes": 200,
    "total_bytes": 1200,
    "physical_unique_bytes": 900,
    "estimated": False,
}
_POSTGRES_FOOTPRINT_SAMPLE: dict[str, Any] = {
    "documents_bytes": 10,
    "ir_blocks_bytes": 20,
    "enrichment_bytes": 5,
    "chunks_bytes": 30,
    "metadata_bytes": 3,
    "observability_bytes": 2,
    "total_bytes": 70,
    "estimated": True,
}
_QDRANT_FOOTPRINT_SAMPLE: dict[str, Any] = {
    "points": 42,
    "dense_bytes": 400,
    "sparse_bytes": 100,
    "payload_bytes": 50,
    "total_bytes": 550,
    "estimated": True,
}
_STORAGE_SAMPLE: dict[str, Any] = {
    "collection_id": CID,
    "s3": _S3_FOOTPRINT_SAMPLE,
    "postgres": _POSTGRES_FOOTPRINT_SAMPLE,
    "qdrant": _QDRANT_FOOTPRINT_SAMPLE,
    "grand_total_bytes": 1520,
    "documents": [
        {
            "document_id": "33333333-3333-3333-3333-333333333333",
            "filename": "report.pdf",
            "s3": _S3_FOOTPRINT_SAMPLE,
            "postgres": _POSTGRES_FOOTPRINT_SAMPLE,
            "qdrant": _QDRANT_FOOTPRINT_SAMPLE,
            "total_bytes": 1820,
        }
    ],
}


@respx.mock
async def test_storage_returns_typed_footprint() -> None:
    route = respx.get(f"{API}/collections/{CID}/storage").mock(
        return_value=httpx.Response(200, json=_STORAGE_SAMPLE)
    )
    async with AsyncClient(BASE) as client:
        result = await client.collections.storage(CID)
    assert route.calls.last.request.method == "GET"
    assert route.calls.last.request.url.path == f"/api/v1/collections/{CID}/storage"
    assert result.grand_total_bytes == 1520
    assert result.documents[0].filename == "report.pdf"


@respx.mock
def test_sync_storage_returns_typed_footprint() -> None:
    route = respx.get(f"{API}/collections/{CID}/storage").mock(
        return_value=httpx.Response(200, json=_STORAGE_SAMPLE)
    )
    with Client(BASE) as client:
        result = client.collections.storage(CID)
    assert route.calls.last.request.method == "GET"
    assert result.s3.estimated is False
    assert result.postgres.estimated is True
