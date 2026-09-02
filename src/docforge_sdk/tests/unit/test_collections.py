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
    CollectionListItem,
    CollectionModel,
    CreateCollectionRequest,
    UpdateCollectionRequest,
)
from docforge_sdk.models.health import CollectionHealthResponse

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

_COLLECTION_LIST_ITEM_SAMPLE: dict[str, Any] = {
    **_COLLECTION_SAMPLE,
    "health": {
        "verdict": "operational",
        "doc_count": 3,
        "chunk_count": 42,
        "last_ingest_at": "2026-01-02T00:00:00Z",
    },
}

_HEALTH_SAMPLE: dict[str, Any] = {
    "collection_id": CID,
    "verdict": "degraded",
    "reason": "The configured embedder is unreachable.",
    "checked_at": "2026-01-03T00:00:00Z",
    "ingest": {"buildable": True, "build_error": None, "providers": []},
    "search": {
        "buildable": True,
        "search_operational": "degraded",
        "build_error": None,
        "providers": [
            {
                "node_id": "embed_query",
                "kind": "bge_server",
                "family": "embed",
                "side": "search",
                "status": "unreachable",
                "endpoint": "http://bge:8080",
                "detail": "connection refused",
                "latency_ms": None,
            }
        ],
        "index": {"vector_count": 42, "last_ingest_at": "2026-01-02T00:00:00Z"},
    },
}


@respx.mock
async def test_list_returns_typed_list() -> None:
    route = respx.get(f"{API}/collections").mock(
        return_value=httpx.Response(200, json=[_COLLECTION_LIST_ITEM_SAMPLE])
    )
    async with AsyncClient(BASE) as client:
        result = await client.collections.list()
    assert route.calls.last.request.method == "GET"
    assert len(result) == 1 and isinstance(result[0], CollectionListItem)
    assert result[0].health.verdict == "operational"
    assert result[0].health.chunk_count == 42


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
        result = client.collections.delete(CID)  # type: ignore[func-returns-value]
    assert route.calls.last.request.method == "DELETE"
    assert result is None


@respx.mock
async def test_health_returns_typed_response() -> None:
    route = respx.get(f"{API}/collections/{CID}/health").mock(
        return_value=httpx.Response(200, json=_HEALTH_SAMPLE)
    )
    async with AsyncClient(BASE) as client:
        result = await client.collections.health(CID)
    assert route.calls.last.request.method == "GET"
    assert route.calls.last.request.url.path == f"/api/v1/collections/{CID}/health"
    assert isinstance(result, CollectionHealthResponse)
    assert result.verdict == "degraded"
    assert result.search.providers[0].status == "unreachable"


@respx.mock
def test_sync_health_returns_typed_response() -> None:
    route = respx.get(f"{API}/collections/{CID}/health").mock(
        return_value=httpx.Response(200, json=_HEALTH_SAMPLE)
    )
    with Client(BASE) as client:
        result = client.collections.health(CID)
    assert route.calls.last.request.method == "GET"
    assert result.ingest.buildable is True


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


_ESTIMATE_SAMPLE: dict[str, Any] = {
    "document_count": 3,
    "stages": [
        {
            "stage": "embed",
            "family": "embed",
            "provider": "bge_server",
            "model": "bge-m3",
            "calls": 12,
            "prompt_tokens": 6000,
            "completion_tokens": 0,
            "pages": 0,
            "cost_usd": 0.0,
            "rate_known": True,
        }
    ],
    "volume": {
        "pages": 30,
        "chunks": 12,
        "dense_vectors": 12,
        "sparse_vectors": 12,
        "storage_bytes": 50000,
    },
    "total_prompt_tokens": 6000,
    "total_completion_tokens": 0,
    "total_cost_usd": 0.0,
    "cost_complete": True,
    "assumptions": {},
    "caveats": ["Figure count is unknown until parse."],
}


@respx.mock
async def test_estimate_posts_scope_and_returns_typed_estimate() -> None:
    route = respx.post(f"{API}/collections/{CID}/estimate").mock(
        return_value=httpx.Response(200, json=_ESTIMATE_SAMPLE)
    )
    async with AsyncClient(BASE) as client:
        result = await client.collections.estimate(CID, scope="all")
    assert route.calls.last.request.method == "POST"
    assert route.calls.last.request.url.path == f"/api/v1/collections/{CID}/estimate"
    assert json.loads(route.calls.last.request.content) == {"scope": "all"}
    assert result.document_count == 3
    assert result.stages[0].provider == "bge_server"
    assert result.assumptions.target_chunk_tokens == 512


@respx.mock
def test_sync_estimate_defaults_to_pending_scope() -> None:
    route = respx.post(f"{API}/collections/{CID}/estimate").mock(
        return_value=httpx.Response(200, json=_ESTIMATE_SAMPLE)
    )
    with Client(BASE) as client:
        result = client.collections.estimate(CID)
    assert json.loads(route.calls.last.request.content) == {"scope": "pending"}
    assert result.cost_complete is True
    assert result.volume.chunks == 12
