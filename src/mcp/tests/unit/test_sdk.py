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


async def test_get_collection_limits_path() -> None:
    """sdk.limits.get issues GET /api/v1/collections/{id}/limits."""
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(200, json={"collection_id": "c1", "in_flight": 0, "budget_spent_usd": 0.0})

    await _client(handler).limits.get("c1")
    assert seen == {"method": "GET", "path": "/api/v1/collections/c1/limits"}


async def test_update_collection_limits_path_and_body() -> None:
    """sdk.limits.update issues PUT /api/v1/collections/{id}/limits with caps in the body."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["path"] = req.url.path
        captured["json"] = json.loads(req.content)
        return httpx.Response(200, json={"collection_id": "c1", "in_flight": 0, "budget_spent_usd": 0.0})

    await _client(handler).limits.update("c1", max_in_flight=5, budget_cap_usd=10.0)
    assert captured["method"] == "PUT"
    assert captured["path"] == "/api/v1/collections/c1/limits"
    assert captured["json"] == {"max_in_flight": 5, "budget_cap_usd": 10.0}


async def test_update_collection_limits_null_caps() -> None:
    """sdk.limits.update sends null values to clear caps (unlimited) — not omits them."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(req.content)
        return httpx.Response(200, json={"collection_id": "c1", "in_flight": 0, "budget_spent_usd": 0.0})

    await _client(handler).limits.update("c1", max_in_flight=None, budget_cap_usd=None)
    # Both keys must be present in the body as null (not omitted) so the server replaces both caps
    assert "max_in_flight" in captured["json"]
    assert "budget_cap_usd" in captured["json"]
    assert captured["json"]["max_in_flight"] is None
    assert captured["json"]["budget_cap_usd"] is None


async def test_get_monitoring_resources_path() -> None:
    """sdk.monitoring.resources issues GET /api/v1/monitoring/resources."""
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(200, json={"device": {}, "limits": {}, "queue_depth": 0, "running": 0, "counts": {}})

    await _client(handler).monitoring.resources()
    assert seen == {"method": "GET", "path": "/api/v1/monitoring/resources"}


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


async def test_authorization_header_sent_when_token_set() -> None:
    """Every outbound request carries 'Authorization: Bearer <token>' when an api_token is provided."""
    captured: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        # Record the raw Authorization header value (empty string if absent)
        captured["auth"] = req.headers.get("authorization", "")
        return httpx.Response(200, json={"collections": [], "total": 0})

    await _client(handler, api_token="my-secret-token").collections.list()
    assert captured["auth"] == "Bearer my-secret-token"


async def test_authorization_header_absent_when_token_empty() -> None:
    """No Authorization header is attached when api_token is empty (backward-compatible with auth-disabled API)."""
    captured: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        # httpx.Headers.get returns None when the key is absent
        captured["auth"] = req.headers.get("authorization", "ABSENT")
        return httpx.Response(200, json={"collections": [], "total": 0})

    await _client(handler, api_token="").collections.list()
    assert captured["auth"] == "ABSENT"


# ---------------------------------------------------------------------------
# Auth sub-API
# ---------------------------------------------------------------------------


async def test_auth_login_path_and_body() -> None:
    """sdk.auth.login posts {username, password} to POST /api/v1/auth/login."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["path"] = req.url.path
        captured["json"] = json.loads(req.content)
        return httpx.Response(200, json={"access_token": "jwt", "token_type": "bearer", "user": {}})

    await _client(handler).auth.login("alice", "s3cr3t")
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/auth/login"
    assert captured["json"] == {"username": "alice", "password": "s3cr3t"}


async def test_auth_me_path() -> None:
    """sdk.auth.me issues GET /api/v1/auth/me."""
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(200, json={"user": {}, "grants": []})

    await _client(handler).auth.me()
    assert seen == {"method": "GET", "path": "/api/v1/auth/me"}


async def test_auth_create_api_key_path_and_body() -> None:
    """sdk.auth.create_api_key posts {name} to POST /api/v1/auth/keys."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["path"] = req.url.path
        captured["json"] = json.loads(req.content)
        return httpx.Response(201, json={"id": "k1", "name": "ci", "prefix": "df_", "key": "plaintext", "created_at": "2024-01-01T00:00:00Z"})

    await _client(handler).auth.create_api_key("ci")
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/auth/keys"
    assert captured["json"] == {"name": "ci"}


async def test_auth_list_api_keys_path() -> None:
    """sdk.auth.list_api_keys issues GET /api/v1/auth/keys."""
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(200, json={"keys": [], "total": 0})

    await _client(handler).auth.list_api_keys()
    assert seen == {"method": "GET", "path": "/api/v1/auth/keys"}


async def test_auth_revoke_api_key_path() -> None:
    """sdk.auth.revoke_api_key issues DELETE /api/v1/auth/keys/{key_id}."""
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(200, json={"revoked": True, "id": "k9"})

    await _client(handler).auth.revoke_api_key("k9")
    assert seen == {"method": "DELETE", "path": "/api/v1/auth/keys/k9"}


# ---------------------------------------------------------------------------
# Users sub-API
# ---------------------------------------------------------------------------


async def test_users_create_path_and_body() -> None:
    """sdk.users.create posts {username, password, role} to POST /api/v1/users."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["path"] = req.url.path
        captured["json"] = json.loads(req.content)
        return httpx.Response(201, json={"id": "u1", "username": "bob", "role": "user", "is_active": True, "created_at": "2024-01-01T00:00:00Z"})

    await _client(handler).users.create("bob", "pass123", role="user")
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/users"
    assert captured["json"] == {"username": "bob", "password": "pass123", "role": "user"}


async def test_users_list_path() -> None:
    """sdk.users.list issues GET /api/v1/users."""
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(200, json={"users": [], "total": 0})

    await _client(handler).users.list()
    assert seen == {"method": "GET", "path": "/api/v1/users"}


async def test_users_deactivate_path() -> None:
    """sdk.users.deactivate issues DELETE /api/v1/users/{user_id}."""
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(200, json={"deactivated": True, "id": "u5"})

    await _client(handler).users.deactivate("u5")
    assert seen == {"method": "DELETE", "path": "/api/v1/users/u5"}


async def test_users_reset_password_path_and_body() -> None:
    """sdk.users.reset_password issues PUT /api/v1/users/{user_id}/password with {password}."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["path"] = req.url.path
        captured["json"] = json.loads(req.content)
        return httpx.Response(200, json={"id": "u5", "username": "bob", "role": "user", "is_active": True, "created_at": "2024-01-01T00:00:00Z"})

    await _client(handler).users.reset_password("u5", "newpass")
    assert captured["method"] == "PUT"
    assert captured["path"] == "/api/v1/users/u5/password"
    assert captured["json"] == {"password": "newpass"}


# ---------------------------------------------------------------------------
# Access sub-API
# ---------------------------------------------------------------------------


async def test_access_list_path() -> None:
    """sdk.access.list issues GET /api/v1/collections/{id}/access."""
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(200, json={"collection_id": "c1", "grants": [], "total": 0})

    await _client(handler).access.list("c1")
    assert seen == {"method": "GET", "path": "/api/v1/collections/c1/access"}


async def test_access_set_path_and_body() -> None:
    """sdk.access.set issues PUT /api/v1/collections/{id}/access/{user_id} with {role}."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["path"] = req.url.path
        captured["json"] = json.loads(req.content)
        return httpx.Response(200, json={"user_id": "u1", "role": "write", "granted_by": None, "created_at": "2024-01-01T00:00:00Z"})

    await _client(handler).access.set("c1", "u1", "write")
    assert captured["method"] == "PUT"
    assert captured["path"] == "/api/v1/collections/c1/access/u1"
    assert captured["json"] == {"role": "write"}


async def test_access_revoke_path() -> None:
    """sdk.access.revoke issues DELETE /api/v1/collections/{id}/access/{user_id}."""
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(200, json={"revoked": True, "collection_id": "c1", "user_id": "u1"})

    await _client(handler).access.revoke("c1", "u1")
    assert seen == {"method": "DELETE", "path": "/api/v1/collections/c1/access/u1"}
