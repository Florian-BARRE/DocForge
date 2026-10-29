# ====== Code Summary ======
# Contract tests over the real streamable-HTTP wire: the mcp 1.x Python client and raw JSON-RPC
# POSTs against the served app (build_mcp + build_http_app). Pins what today's clients rely on:
# the negotiated protocol version, stateless calls under every handshake-era Mcp-Protocol-Version
# header (or none), the result shapes (compact text, inline image), the error shapes (SDK 404,
# unknown argument), the bearer gate (401 + WWW-Authenticate), per-caller bearer isolation and
# the raised request-body ceiling.

from __future__ import annotations

# ====== Standard Library Imports ======
import asyncio
import base64
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

# ====== Third-Party Library Imports ======
import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import ImageContent, TextContent

# ====== Internal Project Imports ======
from conftest import COLLECTION_ID, IMAGE_BLOB_HASH, PNG_BYTES, ContractServer

_ACCEPT = "application/json, text/event-stream"

# streamablehttp_client is the 1.x name the OpenAI Agents SDK still calls on mcp 1.x; 1.29 flags it.
pytestmark = pytest.mark.filterwarnings(
    "ignore:Use `streamable_http_client` instead:DeprecationWarning"
)


@asynccontextmanager
async def _session(url: str, token: str = "key-a") -> AsyncIterator[ClientSession]:
    async with streamablehttp_client(url, headers={"Authorization": f"Bearer {token}"}) as (
        read,
        write,
        _,
    ):
        async with ClientSession(read, write) as session:
            yield session


def _rpc(
    url: str, method: str, params: dict[str, Any] | None = None, **headers: str
) -> httpx.Response:
    """One raw stateless JSON-RPC POST (no initialize first), the way a minimal client calls."""
    body: dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        body["params"] = params
    return httpx.post(
        url,
        json=body,
        headers={"Authorization": "Bearer key-a", "Accept": _ACCEPT, **headers},
        timeout=30,
    )


async def test_mcp_1x_client_negotiates_2025_11_25(server: ContractServer) -> None:
    async with _session(server.url) as session:
        init = await session.initialize()
    assert init.protocolVersion == "2025-11-25"
    assert init.serverInfo.name == "DocForge"
    assert init.capabilities.tools is not None


@pytest.mark.parametrize("requested", ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"])
def test_initialize_echoes_every_handshake_era_version(
    server: ContractServer, requested: str
) -> None:
    response = _rpc(
        server.url,
        "initialize",
        {
            "protocolVersion": requested,
            "capabilities": {},
            "clientInfo": {"name": "contract", "version": "0"},
        },
    )
    assert response.status_code == 200
    assert response.json()["result"]["protocolVersion"] == requested


def test_initialize_with_an_unknown_version_gets_the_latest(server: ContractServer) -> None:
    response = _rpc(
        server.url,
        "initialize",
        {
            "protocolVersion": "1999-01-01",
            "capabilities": {},
            "clientInfo": {"name": "contract", "version": "0"},
        },
    )
    assert response.json()["result"]["protocolVersion"] == "2025-11-25"


@pytest.mark.parametrize("header", ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25", None])
def test_stateless_tool_call_succeeds_under_each_protocol_header(
    server: ContractServer, header: str | None
) -> None:
    extra = {"Mcp-Protocol-Version": header} if header else {}
    response = _rpc(server.url, "tools/call", {"name": "ping", "arguments": {}}, **extra)
    assert response.status_code == 200
    # json_response=True: one JSON body per POST, never an SSE stream, no session id.
    assert response.headers["content-type"].startswith("application/json")
    assert "mcp-session-id" not in response.headers
    result = response.json()["result"]
    assert result["isError"] is False
    assert result["content"] == [{"type": "text", "text": '{"status":"ok"}'}]


async def test_protocol_ping_and_a_compact_json_tool(server: ContractServer) -> None:
    async with _session(server.url) as session:
        await session.initialize()
        await session.send_ping()
        result = await session.call_tool("ping", {})
    assert result.isError is False
    assert result.structuredContent is None
    assert [(c.type, c.text) for c in result.content if isinstance(c, TextContent)] == [
        ("text", '{"status":"ok"}')
    ]


async def test_text_mode_tool_returns_one_text_block(server: ContractServer) -> None:
    async with _session(server.url) as session:
        await session.initialize()
        result = await session.call_tool(
            "search_collection", {"collection_id": COLLECTION_ID, "query": "intro"}
        )
    assert result.isError is False
    assert len(result.content) == 1
    block = result.content[0]
    assert isinstance(block, TextContent)
    assert "Hello world." in block.text


async def test_get_blob_returns_an_inline_image(server: ContractServer) -> None:
    async with _session(server.url) as session:
        await session.initialize()
        result = await session.call_tool("get_blob", {"content_hash": IMAGE_BLOB_HASH})
    assert result.isError is False
    block = result.content[0]
    assert isinstance(block, ImageContent)
    assert block.mimeType == "image/png"
    assert base64.b64decode(block.data) == PNG_BYTES


async def test_sdk_404_is_a_tool_error_carrying_the_api_status(server: ContractServer) -> None:
    async with _session(server.url) as session:
        await session.initialize()
        result = await session.call_tool("get_document", {"document_id": "missing"})
    assert result.isError is True
    text = result.content[0]
    assert isinstance(text, TextContent)
    assert "DocForge API error 404" in text.text
    assert "nope" in text.text


async def test_unknown_argument_is_rejected_as_extra_forbidden(server: ContractServer) -> None:
    async with _session(server.url) as session:
        await session.initialize()
        result = await session.call_tool("ping", {"bogus": 1})
    assert result.isError is True
    text = result.content[0]
    assert isinstance(text, TextContent)
    assert "extra_forbidden" in text.text
    assert server.api.calls == [], "a rejected call never reaches DocForge"


def test_missing_bearer_is_401_with_www_authenticate(server: ContractServer) -> None:
    response = httpx.post(
        server.url,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={"Accept": _ACCEPT},
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("authorization", ["Basic dXNlcjpwYXNz", "Token key-a", "Bearer", ""])
def test_non_bearer_or_empty_authorization_is_401(
    server: ContractServer, authorization: str
) -> None:
    response = _rpc(server.url, "tools/list", Authorization=authorization)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_concurrent_bearers_each_reach_their_own_sdk_client(server: ContractServer) -> None:
    async def whoami(token: str) -> str:
        async with _session(server.url, token) as session:
            await session.initialize()
            result = await session.call_tool("whoami", {})
        block = result.content[0]
        assert isinstance(block, TextContent)
        collections: list[str] = json.loads(block.text)["collections"]
        return collections[0]

    tokens = [f"key-{n}" for n in range(8)]
    seen = await asyncio.gather(*(whoami(token) for token in tokens))
    assert seen == tokens
    whoami_auth = sorted(auth for auth, path in server.api.calls if path.endswith("/whoami"))
    assert whoami_auth == sorted(f"Bearer {token}" for token in tokens)


def test_a_5_mib_base64_upload_is_not_413(server: ContractServer) -> None:
    content = base64.b64encode(b"\0" * (5 * 1024 * 1024)).decode()
    response = _rpc(
        server.url,
        "tools/call",
        {
            "name": "upload_document_bytes",
            "arguments": {
                "collection_id": COLLECTION_ID,
                "filename": "big.pdf",
                "content_base64": content,
            },
        },
    )
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is False
    assert json.loads(result["content"][0]["text"])["document_id"] == "d-new"
