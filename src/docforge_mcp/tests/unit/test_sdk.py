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


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> DocForgeClient:
    """Build a client whose transport is backed by a httpx MockTransport handler."""
    client = DocForgeClient("http://api", timeout=5.0)
    # Swap the pooled client for a mock-backed one (private poke is fine in a unit test).
    client._transport._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


async def test_list_collections_path() -> None:
    """sdk.collections.list issues GET /api/v1/collections/list."""
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(200, json={"collections": [], "total": 0})

    await _client(handler).collections.list()
    assert seen == {"method": "GET", "path": "/api/v1/collections/list"}


async def test_search_collection_body() -> None:
    """sdk.search.collection posts the full SearchRequest body to the right path."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["path"] = req.url.path
        captured["json"] = json.loads(req.content)
        return httpx.Response(200, json={"results": []})

    await _client(handler).search.collection(
        "c1", "hello", top_k=5, filters={"must": []}, weights={"dense-text": 0.7}, debug=True
    )
    assert captured["path"] == "/api/v1/collections/c1/documents/search"
    body = captured["json"]
    assert body["query"] == "hello"
    assert body["top_k"] == 5
    assert body["debug"] is True
    assert body["filters"] == {"must": []}
    assert body["weights"] == {"dense-text": 0.7}


async def test_delete_collection_path() -> None:
    """sdk.collections.delete issues DELETE on the collection delete path."""
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(200, json={"deleted": True})

    await _client(handler).collections.delete("c9")
    assert seen == {"method": "DELETE", "path": "/api/v1/collections/c9/delete"}


async def test_config_update_path_and_body() -> None:
    """sdk.config.update posts {patch, note} to the config update path."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["path"] = req.url.path
        captured["json"] = json.loads(req.content)
        return httpx.Response(200, json={"id": "c1"})

    await _client(handler).config.update("c1", {"pipeline": {}}, note="tweak")
    assert captured["path"] == "/api/v1/collections/c1/config/update"
    assert captured["json"] == {"patch": {"pipeline": {}}, "note": "tweak"}


async def test_non_2xx_raises_runtimeerror() -> None:
    """A non-2xx response surfaces as a RuntimeError carrying the status code."""

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    with pytest.raises(RuntimeError, match="404"):
        await _client(handler).documents.get("c1", "d1")
