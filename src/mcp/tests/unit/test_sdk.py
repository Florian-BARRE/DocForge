# ====== Code Summary ======
# Unit tests for the DocForge SDK: verb + path construction, request bodies, and error raising.
# A httpx MockTransport intercepts requests so no real DocForge server is needed.

from __future__ import annotations

# ====== Standard Library Imports ======
import json
from collections.abc import Callable
from typing import Any

# ====== Third-Party Library Imports ======
import httpx
import pytest

# ====== Internal Project Imports ======
from libs.sdk import DocForgeClient


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
    api_token: str = "",
) -> DocForgeClient:
    """Build a client whose transport is backed by a httpx MockTransport handler.

    Args:
        handler: Request interceptor returning a canned response.
        api_token: Optional bearer token; forwarded to DocForgeTransport so default-header
            logic is exercised even after swapping in the mock transport.
    """
    client = DocForgeClient("http://api", timeout=5.0, api_token=api_token)
    # Swap the pooled client for a mock-backed one (private poke is fine in a unit test).
    # Preserve the default_headers already set by DocForgeTransport so the Authorization
    # header (when a token was supplied) survives the swap.
    client._transport._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers=dict(client._transport._http.headers),
    )
    return client


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


async def test_health_ping_path_is_public() -> None:
    """sdk.health.ping issues GET /health — NOT prefixed with /api/v1 (public probe)."""
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(200, json={"status": "ok"})

    await _client(handler).health.ping()
    assert seen == {"method": "GET", "path": "/health"}


# ---------------------------------------------------------------------------
# Transport verbs
# ---------------------------------------------------------------------------


async def test_transport_put_verb() -> None:
    """transport.put issues an HTTP PUT with the correct JSON body."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["json"] = json.loads(req.content)
        return httpx.Response(200, json={"ok": True})

    client = _client(handler)
    await client._transport.put("/some/path", {"key": "value"})
    assert captured["method"] == "PUT"
    assert captured["json"] == {"key": "value"}


async def test_transport_patch_verb() -> None:
    """transport.patch issues an HTTP PATCH with the correct JSON body."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["json"] = json.loads(req.content)
        return httpx.Response(200, json={"ok": True})

    client = _client(handler)
    await client._transport.patch("/some/path", {"enabled": True})
    assert captured["method"] == "PATCH"
    assert captured["json"] == {"enabled": True}


async def test_non_2xx_raises_runtimeerror() -> None:
    """A non-2xx response surfaces as a RuntimeError carrying the status code."""

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    with pytest.raises(RuntimeError, match="404"):
        await _client(handler).explorer.get_document("d1")


async def test_authorization_header_sent_when_token_set() -> None:
    """Every outbound request carries 'Authorization: Bearer <token>' when an api_token is provided."""
    captured: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        # Record the raw Authorization header value (empty string if absent)
        captured["auth"] = req.headers.get("authorization", "")
        return httpx.Response(200, json=[])

    await _client(handler, api_token="my-secret-token").collections.list()
    assert captured["auth"] == "Bearer my-secret-token"


async def test_authorization_header_absent_when_token_empty() -> None:
    """No Authorization header is attached when api_token is empty (backward-compatible with auth-disabled API)."""
    captured: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        # httpx.Headers.get returns None when the key is absent
        captured["auth"] = req.headers.get("authorization", "ABSENT")
        return httpx.Response(200, json=[])

    await _client(handler, api_token="").collections.list()
    assert captured["auth"] == "ABSENT"


# ---------------------------------------------------------------------------
# Collections sub-API
# ---------------------------------------------------------------------------


async def test_list_collections_path() -> None:
    """sdk.collections.list issues GET /api/v1/collections."""
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(200, json=[])

    await _client(handler).collections.list()
    assert seen == {"method": "GET", "path": "/api/v1/collections"}


async def test_get_collection_path() -> None:
    """sdk.collections.get issues GET /api/v1/collections/{id}."""
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(200, json={"id": "c1"})

    await _client(handler).collections.get("c1")
    assert seen == {"method": "GET", "path": "/api/v1/collections/c1"}


async def test_create_collection_path_and_body() -> None:
    """sdk.collections.create posts the full CreateCollectionRequest body."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["path"] = req.url.path
        captured["json"] = json.loads(req.content)
        return httpx.Response(201, json={"id": "c1"})

    await _client(handler).collections.create(
        "docs", ["pdf"], 100_000_000, fields=[{"field_name": "title", "field_type": "string"}]
    )
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/collections"
    assert captured["json"] == {
        "name": "docs",
        "supported_formats": ["pdf"],
        "max_file_size_bytes": 100_000_000,
        "fields": [{"field_name": "title", "field_type": "string"}],
    }


async def test_update_collection_path_and_body() -> None:
    """sdk.collections.update patches only the provided (non-None) knobs."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["path"] = req.url.path
        captured["json"] = json.loads(req.content)
        return httpx.Response(200, json={"id": "c1"})

    await _client(handler).collections.update("c1", name="renamed", note="tweak")
    assert captured["method"] == "PATCH"
    assert captured["path"] == "/api/v1/collections/c1"
    assert captured["json"] == {"name": "renamed", "note": "tweak"}


async def test_delete_collection_path() -> None:
    """sdk.collections.delete issues DELETE /api/v1/collections/{id}."""
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(204)

    await _client(handler).collections.delete("c9")
    assert seen == {"method": "DELETE", "path": "/api/v1/collections/c9"}


# ---------------------------------------------------------------------------
# Documents sub-API (admission)
# ---------------------------------------------------------------------------


async def test_set_document_enabled_path_and_body() -> None:
    """sdk.documents.set_enabled issues PATCH /api/v1/documents/{id}/enabled with {enabled}."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["path"] = req.url.path
        captured["json"] = json.loads(req.content)
        return httpx.Response(200, json={"document_id": "d1", "enabled": False})

    await _client(handler).documents.set_enabled("d1", False)
    assert captured["method"] == "PATCH"
    assert captured["path"] == "/api/v1/documents/d1/enabled"
    assert captured["json"] == {"enabled": False}


# ---------------------------------------------------------------------------
# Explorer sub-API
# ---------------------------------------------------------------------------


async def test_list_documents_path() -> None:
    """sdk.explorer.list_documents issues GET /api/v1/collections/{id}/documents."""
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(200, json=[])

    await _client(handler).explorer.list_documents("c1")
    assert seen == {"method": "GET", "path": "/api/v1/collections/c1/documents"}


async def test_get_document_chunks_path() -> None:
    """sdk.explorer.get_chunks issues GET /api/v1/documents/{id}/chunks."""
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(200, json=[])

    await _client(handler).explorer.get_chunks("d1")
    assert seen == {"method": "GET", "path": "/api/v1/documents/d1/chunks"}


async def test_set_chunks_enabled_bulk_path_and_body() -> None:
    """sdk.explorer.set_chunks_enabled issues PATCH /api/v1/chunks/enabled with the bulk body."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["path"] = req.url.path
        captured["json"] = json.loads(req.content)
        return httpx.Response(200, json={"results": [], "not_found": []})

    await _client(handler).explorer.set_chunks_enabled(["ck1", "ck2"], True)
    assert captured["method"] == "PATCH"
    assert captured["path"] == "/api/v1/chunks/enabled"
    assert captured["json"] == {"chunk_ids": ["ck1", "ck2"], "enabled": True}


async def test_delete_document_path() -> None:
    """sdk.explorer.delete_document issues DELETE /api/v1/documents/{id}."""
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(204)

    await _client(handler).explorer.delete_document("d1")
    assert seen == {"method": "DELETE", "path": "/api/v1/documents/d1"}


# ---------------------------------------------------------------------------
# Search sub-API
# ---------------------------------------------------------------------------


async def test_search_collection_path_and_body() -> None:
    """sdk.search.search posts the SearchRequest body to POST /api/v1/collections/{id}/search."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["path"] = req.url.path
        captured["json"] = json.loads(req.content)
        return httpx.Response(200, json={"query": "hello", "hits": []})

    await _client(handler).search.search(
        "c1",
        "hello",
        limit=5,
        filters={"lang": "en"},
        search_in=[{"field": "content", "semantic": True, "lexical": True}],
        use_late_interaction=True,
        rescore_pool_size=50,
    )
    assert captured["path"] == "/api/v1/collections/c1/search"
    body = captured["json"]
    assert body["query"] == "hello"
    assert body["limit"] == 5
    assert body["filters"] == {"lang": "en"}
    assert body["search_in"] == [{"field": "content", "semantic": True, "lexical": True}]
    assert body["use_late_interaction"] is True
    assert body["rescore_pool_size"] == 50


# ---------------------------------------------------------------------------
# Jobs sub-API
# ---------------------------------------------------------------------------


async def test_list_jobs_requires_collection_id() -> None:
    """sdk.jobs.list issues GET /api/v1/jobs?collection_id=... (required by the API)."""
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        seen["query"] = dict(req.url.params)
        return httpx.Response(200, json=[])

    await _client(handler).jobs.list("c1")
    assert seen["path"] == "/api/v1/jobs"
    assert seen["query"] == {"collection_id": "c1"}


async def test_get_job_events_path() -> None:
    """sdk.jobs.get_events issues GET /api/v1/jobs/{id}/events."""
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(200, json={"job_id": "j1", "events": []})

    await _client(handler).jobs.get_events("j1")
    assert seen == {"method": "GET", "path": "/api/v1/jobs/j1/events"}


async def test_live_workers_path() -> None:
    """sdk.jobs.live_workers issues GET /api/v1/jobs/workers/live."""
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(200, json={"workers": []})

    await _client(handler).jobs.live_workers()
    assert seen == {"method": "GET", "path": "/api/v1/jobs/workers/live"}


# ---------------------------------------------------------------------------
# Blobs sub-API
# ---------------------------------------------------------------------------


async def test_get_blob_returns_bytes_and_mime_type() -> None:
    """sdk.blobs.get issues GET /api/v1/blobs/{hash} and returns (bytes, content-type)."""
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        return httpx.Response(200, content=b"\x89PNG...", headers={"content-type": "image/png"})

    data, mime_type = await _client(handler).blobs.get("abc123")
    assert seen["path"] == "/api/v1/blobs/abc123"
    assert data == b"\x89PNG..."
    assert mime_type == "image/png"


# ---------------------------------------------------------------------------
# Pipelines sub-API
# ---------------------------------------------------------------------------


async def test_list_pipeline_surfaces_path() -> None:
    """sdk.pipelines.list_surfaces issues GET /api/v1/pipelines."""
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(200, json={"pipelines": []})

    await _client(handler).pipelines.list_surfaces()
    assert seen == {"method": "GET", "path": "/api/v1/pipelines"}


async def test_get_pipeline_design_path_and_query() -> None:
    """sdk.pipelines.get_design issues GET /api/v1/pipelines/{key}?full=..."""
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        seen["query"] = dict(req.url.params)
        return httpx.Response(200, json={"palette": {}, "blob": {}, "issues": []})

    await _client(handler).pipelines.get_design("ingest", full=True)
    assert seen["path"] == "/api/v1/pipelines/ingest"
    assert seen["query"] == {"full": "true"}


# ---------------------------------------------------------------------------
# Auth sub-API
# ---------------------------------------------------------------------------


async def test_auth_create_key_path_and_body() -> None:
    """sdk.auth.create_key posts {name} to POST /api/v1/auth/keys (permissions omitted when None)."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["path"] = req.url.path
        captured["json"] = json.loads(req.content)
        return httpx.Response(
            201,
            json={
                "id": "k1", "name": "ci", "prefix": "df_", "permissions": None,
                "created_at": "2024-01-01T00:00:00Z", "key": "plaintext",
            },
        )

    await _client(handler).auth.create_key("ci")
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/auth/keys"
    assert captured["json"] == {"name": "ci"}


async def test_auth_list_keys_path() -> None:
    """sdk.auth.list_keys issues GET /api/v1/auth/keys."""
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(200, json=[])

    await _client(handler).auth.list_keys()
    assert seen == {"method": "GET", "path": "/api/v1/auth/keys"}


async def test_auth_revoke_key_path() -> None:
    """sdk.auth.revoke_key issues DELETE /api/v1/auth/keys/{key_id}."""
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(204)

    await _client(handler).auth.revoke_key("k9")
    assert seen == {"method": "DELETE", "path": "/api/v1/auth/keys/k9"}
