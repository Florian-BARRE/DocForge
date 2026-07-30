# ====== Code Summary ======
# Auth-resource tests: each method hits the exact URL + HTTP method and returns the right typed model,
# and the rotate path proves the exclude_unset contract — an unset field is omitted from the body while
# an explicit None is serialised as JSON null. Runs against both the async and sync clients.

# ====== Standard Library Imports ======
import json
from datetime import UTC, datetime
from typing import Any

# ====== Third-Party Library Imports ======
import httpx
import respx

# ====== Local Project Imports ======
from docforge_sdk import AsyncClient, Client
from docforge_sdk.models.auth import CreatedKey, KeyInfo

BASE = "http://test"
API = f"{BASE}/api/v1"
KEY_ID = "11111111-1111-1111-1111-111111111111"

_CREATED_SAMPLE: dict[str, Any] = {
    "id": KEY_ID,
    "name": "k",
    "prefix": "df_abc",
    "permissions": None,
    "created_at": "2026-01-01T00:00:00Z",
    "expires_at": None,
    "key": "df_secret_plaintext",
}
_KEY_INFO_SAMPLE: dict[str, Any] = {
    "id": KEY_ID,
    "name": "k",
    "prefix": "df_abc",
    "permissions": None,
    "created_at": "2026-01-01T00:00:00Z",
    "expires_at": None,
    "last_used_at": None,
    "revoked_at": None,
}


def _body(route: respx.Route) -> dict[str, Any]:
    """Decode the JSON body of the last request captured by a route."""
    return json.loads(route.calls.last.request.content)


@respx.mock
async def test_create_key_returns_created_model() -> None:
    route = respx.post(f"{API}/auth/keys").mock(
        return_value=httpx.Response(201, json=_CREATED_SAMPLE)
    )
    async with AsyncClient(BASE, api_token="t") as client:
        result = await client.auth.create_key(name="k")
    assert route.calls.last.request.method == "POST"
    assert isinstance(result, CreatedKey)


@respx.mock
async def test_create_key_body_with_and_without_expiry() -> None:
    route = respx.post(f"{API}/auth/keys").mock(
        return_value=httpx.Response(201, json=_CREATED_SAMPLE)
    )
    async with AsyncClient(BASE) as client:
        await client.auth.create_key(name="k")
        first = _body(route)
        assert "expires_at" in first and first["expires_at"] is None

        moment = datetime(2027, 1, 1, tzinfo=UTC)
        await client.auth.create_key(name="k", expires_at=moment)
        assert _body(route)["expires_at"] is not None


@respx.mock
async def test_list_keys_returns_typed_list() -> None:
    route = respx.get(f"{API}/auth/keys").mock(
        return_value=httpx.Response(200, json=[_KEY_INFO_SAMPLE])
    )
    async with AsyncClient(BASE) as client:
        result = await client.auth.list_keys()
    assert route.calls.last.request.method == "GET"
    assert len(result) == 1 and isinstance(result[0], KeyInfo)


@respx.mock
async def test_revoke_key_hits_delete_and_returns_none() -> None:
    route = respx.delete(f"{API}/auth/keys/{KEY_ID}").mock(return_value=httpx.Response(204))
    async with AsyncClient(BASE) as client:
        result = await client.auth.revoke_key(KEY_ID)
    assert route.calls.last.request.method == "DELETE"
    assert result is None


@respx.mock
async def test_rotate_name_only_omits_other_fields() -> None:
    route = respx.post(f"{API}/auth/keys/{KEY_ID}/rotate").mock(
        return_value=httpx.Response(201, json=_CREATED_SAMPLE)
    )
    async with AsyncClient(BASE) as client:
        result = await client.auth.rotate_key(KEY_ID, name="x")
    assert route.calls.last.request.url.path == f"/api/v1/auth/keys/{KEY_ID}/rotate"
    assert _body(route) == {"name": "x"}
    assert isinstance(result, CreatedKey)


@respx.mock
async def test_rotate_explicit_none_permissions_sends_null() -> None:
    route = respx.post(f"{API}/auth/keys/{KEY_ID}/rotate").mock(
        return_value=httpx.Response(201, json=_CREATED_SAMPLE)
    )
    async with AsyncClient(BASE) as client:
        await client.auth.rotate_key(KEY_ID, permissions=None)
    body = _body(route)
    assert body == {"permissions": None}


@respx.mock
async def test_rotate_no_args_sends_empty_body() -> None:
    route = respx.post(f"{API}/auth/keys/{KEY_ID}/rotate").mock(
        return_value=httpx.Response(201, json=_CREATED_SAMPLE)
    )
    async with AsyncClient(BASE) as client:
        await client.auth.rotate_key(KEY_ID)
    assert _body(route) == {}


@respx.mock
def test_sync_rotate_name_only_omits_other_fields() -> None:
    route = respx.post(f"{API}/auth/keys/{KEY_ID}/rotate").mock(
        return_value=httpx.Response(201, json=_CREATED_SAMPLE)
    )
    with Client(BASE) as client:
        client.auth.rotate_key(KEY_ID, name="x")
    assert _body(route) == {"name": "x"}
