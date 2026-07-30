# ====== Code Summary ======
# Transport-level tests covering both AsyncTransport and SyncTransport: a 200 parses into the model,
# error statuses map to the right exceptions, the Authorization header is present iff a token was
# given, and None-valued query params are dropped before the request is sent.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
import httpx
import pytest
import respx

# ====== Local Project Imports ======
from docforge_sdk._exceptions import (
    AuthError,
    ConflictError,
    NotFoundError,
    UnprocessableError,
)
from docforge_sdk._requestspec import RequestSpec
from docforge_sdk._transport import AsyncTransport, SyncTransport
from docforge_sdk.models.auth import CreatedKey

BASE = "http://test"
API = f"{BASE}/api/v1"

_CREATED_SAMPLE: dict[str, Any] = {
    "id": "11111111-1111-1111-1111-111111111111",
    "name": "k",
    "prefix": "df_abc",
    "permissions": None,
    "created_at": "2026-01-01T00:00:00Z",
    "expires_at": None,
    "key": "df_secret_plaintext",
}


@respx.mock
async def test_async_200_parses_into_model() -> None:
    respx.post(f"{API}/auth/keys").mock(return_value=httpx.Response(201, json=_CREATED_SAMPLE))
    transport = AsyncTransport(BASE, 5.0, api_token="tok")
    result = await transport.request(RequestSpec("POST", "/auth/keys", json={"name": "k"}), CreatedKey)
    assert isinstance(result, CreatedKey)
    assert result.key == "df_secret_plaintext"
    await transport.aclose()


@respx.mock
def test_sync_200_parses_into_model() -> None:
    respx.post(f"{API}/auth/keys").mock(return_value=httpx.Response(201, json=_CREATED_SAMPLE))
    transport = SyncTransport(BASE, 5.0, api_token="tok")
    result = transport.request(RequestSpec("POST", "/auth/keys", json={"name": "k"}), CreatedKey)
    assert isinstance(result, CreatedKey)
    transport.close()


@respx.mock
@pytest.mark.parametrize(
    ("status", "expected"),
    [(404, NotFoundError), (401, AuthError), (403, AuthError), (409, ConflictError), (422, UnprocessableError)],
)
async def test_async_status_maps_to_exception(status: int, expected: type[Exception]) -> None:
    respx.get(f"{API}/auth/keys").mock(return_value=httpx.Response(status, json={"detail": "x"}))
    transport = AsyncTransport(BASE, 5.0)
    with pytest.raises(expected):
        await transport.request(RequestSpec("GET", "/auth/keys"), CreatedKey)
    await transport.aclose()


@respx.mock
@pytest.mark.parametrize(
    ("status", "expected"),
    [(404, NotFoundError), (401, AuthError), (409, ConflictError), (422, UnprocessableError)],
)
def test_sync_status_maps_to_exception(status: int, expected: type[Exception]) -> None:
    respx.get(f"{API}/auth/keys").mock(return_value=httpx.Response(status, json={"detail": "x"}))
    transport = SyncTransport(BASE, 5.0)
    with pytest.raises(expected):
        transport.request(RequestSpec("GET", "/auth/keys"), CreatedKey)
    transport.close()


@respx.mock
def test_status_error_carries_code_and_body() -> None:
    respx.get(f"{API}/auth/keys").mock(return_value=httpx.Response(404, json={"detail": "gone"}))
    transport = SyncTransport(BASE, 5.0)
    with pytest.raises(NotFoundError) as info:
        transport.request(RequestSpec("GET", "/auth/keys"), CreatedKey)
    assert info.value.status_code == 404
    assert info.value.body == {"detail": "gone"}
    transport.close()


@respx.mock
async def test_authorization_header_present_only_with_token() -> None:
    route = respx.get(f"{API}/auth/keys").mock(return_value=httpx.Response(200, json=_CREATED_SAMPLE))

    with_token = AsyncTransport(BASE, 5.0, api_token="tok")
    await with_token.request(RequestSpec("GET", "/auth/keys"), CreatedKey)
    assert route.calls.last.request.headers.get("authorization") == "Bearer tok"
    await with_token.aclose()

    without_token = AsyncTransport(BASE, 5.0)
    await without_token.request(RequestSpec("GET", "/auth/keys"), CreatedKey)
    assert "authorization" not in route.calls.last.request.headers
    await without_token.aclose()


@respx.mock
def test_clean_drops_none_query_params() -> None:
    route = respx.get(f"{API}/auth/keys").mock(return_value=httpx.Response(200, json=_CREATED_SAMPLE))
    transport = SyncTransport(BASE, 5.0)
    transport.request(RequestSpec("GET", "/auth/keys", params={"a": "1", "b": None}), CreatedKey)
    sent = route.calls.last.request.url
    assert sent.params.get("a") == "1"
    assert "b" not in sent.params
    transport.close()
