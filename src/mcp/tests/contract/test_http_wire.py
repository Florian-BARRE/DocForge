# ====== Code Summary ======
# Contract tests over the real streamable-HTTP wire: the mcp 1.x Python client (a script in a
# throwaway env, see client_env.py), the mcp 2.x `Client` (in-process, both negotiation modes) and
# raw JSON-RPC POSTs against the served app (build_mcp + build_http_app). Pins what clients rely
# on: the negotiated protocol version (2025-11-25 for every handshake-era client, 2026-07-28 for a
# 2.x client in auto mode), stateless calls under every handshake-era Mcp-Protocol-Version header
# (or none), the result shapes (compact text, inline image), the error shapes (SDK 404, unknown
# argument), the bearer gate (401 + WWW-Authenticate), per-caller bearer isolation, a remote Host
# header (DNS-rebinding protection off), the raised request-body ceiling and the tools/list cache
# hint (ttlMs/cacheScope on 2026-07-28 responses only).

from __future__ import annotations

# ====== Standard Library Imports ======
import asyncio
import base64
import json
import shutil
from pathlib import Path
from typing import Any

# ====== Third-Party Library Imports ======
import httpx
import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, ImageContent, TextContent

# ====== Internal Project Imports ======
from client_env import MCP_1X_REQUIREMENT, run_client_script
from conftest import COLLECTION_ID, IMAGE_BLOB_HASH, PNG_BYTES, ContractServer

_ACCEPT = "application/json, text/event-stream"

_MCP1_CLIENT_SCRIPT = Path(__file__).with_name("mcp1_client.py")
_WHOAMI_TOKENS = [f"key-{n}" for n in range(8)]


def _rpc(
    url: str, method: str, params: dict[str, Any] | None = None, /, **headers: str
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


def test_tools_list_carries_the_cache_hint_at_2026_07_28(server: ContractServer) -> None:
    """A 2026-07-28 tools/list (envelope in params._meta, Mcp-Method header) gets ttlMs/cacheScope."""
    headers = {"Mcp-Protocol-Version": "2026-07-28", "Mcp-Method": "tools/list"}
    response = _rpc(
        server.url,
        "tools/list",
        {
            "_meta": {
                "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                "io.modelcontextprotocol/clientCapabilities": {},
            }
        },
        **headers,
    )
    assert response.status_code == 200
    result = response.json()["result"]
    assert (result["ttlMs"], result["cacheScope"]) == (3_600_000, "public")
    assert len(result["tools"]) == 85


@pytest.mark.parametrize("header", ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25", None])
def test_tools_list_carries_no_cache_hint_before_2026(
    server: ContractServer, header: str | None
) -> None:
    """Handshake-era responses stay as they were: the 2026-07-28 fields are sieved out."""
    extra = {"Mcp-Protocol-Version": header} if header else {}
    response = _rpc(server.url, "tools/list", **extra)
    assert response.status_code == 200
    result = response.json()["result"]
    assert set(result) == {"tools"}
    assert len(result["tools"]) == 85


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


def test_a_remote_host_header_is_served(server: ContractServer) -> None:
    """DNS-rebinding protection stays off: a non-localhost Host (a published port) is not 421."""
    response = _rpc(
        server.url, "tools/call", {"name": "ping", "arguments": {}}, Host="docforge.example:10048"
    )
    assert response.status_code == 200
    assert response.json()["result"]["isError"] is False


# ---- Python clients: one report per client, the same assertions for every major and mode ----


def _assert_client_report(report: dict[str, Any], server: ContractServer) -> None:
    """What any Python client sees: identity, catalogue, results, errors, bearer isolation."""
    assert report["server_name"] == "DocForge"
    assert report["has_tools_capability"] is True
    assert report["tool_count"] == 85
    calls = report["calls"]
    assert calls["ping"] == {
        "is_error": False,
        "structured": False,
        "content": [{"type": "text", "text": '{"status":"ok"}'}],
    }
    # Text-mode tool: one text block.
    assert calls["search"]["is_error"] is False
    assert [block["type"] for block in calls["search"]["content"]] == ["text"]
    assert "Hello world." in calls["search"]["content"][0]["text"]
    # get_blob: an inline image.
    assert calls["image"]["is_error"] is False
    (image,) = calls["image"]["content"]
    assert (image["type"], image["mime_type"]) == ("image", "image/png")
    assert base64.b64decode(image["data"]) == PNG_BYTES
    # An SDK 404 is a tool error carrying the API status and detail.
    assert calls["missing"]["is_error"] is True
    assert "DocForge API error 404" in calls["missing"]["content"][0]["text"]
    assert "nope" in calls["missing"]["content"][0]["text"]
    # An unknown argument is rejected before DocForge: the valid ping is the one /health call.
    assert calls["bogus"]["is_error"] is True
    assert "extra_forbidden" in calls["bogus"]["content"][0]["text"]
    assert [path for _, path in server.api.calls if path == "/health"] == ["/health"]
    # Concurrent callers, each with its own bearer, each reach their own SDK client.
    assert report["whoami"]["seen"] == report["whoami"]["tokens"]
    whoami_auth = sorted(auth for auth, path in server.api.calls if path.endswith("/whoami"))
    assert whoami_auth == sorted(f"Bearer {token}" for token in report["whoami"]["tokens"])


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("uv") is None, reason="needs uv to build the client env")
def test_mcp_1x_client_negotiates_2025_11_25(server: ContractServer) -> None:
    """A client locked on mcp 1.x keeps the initialize handshake at 2025-11-25, same results."""
    report = run_client_script(
        [MCP_1X_REQUIREMENT],
        "mcp",
        _MCP1_CLIENT_SCRIPT,
        server.url,
        IMAGE_BLOB_HASH,
        COLLECTION_ID,
    )
    assert report["mcp_version"] == "1.29.1"
    assert report["protocol_version"] == "2025-11-25"
    _assert_client_report(report, server)
    first = server.wire[0]
    assert (first.rpc_method, first.status) == ("initialize", 200)
    assert "server/discover" not in {record.rpc_method for record in server.wire}


def _blocks(result: CallToolResult) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    for block in result.content:
        if isinstance(block, TextContent):
            blocks.append({"type": "text", "text": block.text})
        elif isinstance(block, ImageContent):
            blocks.append({"type": "image", "mime_type": block.mime_type, "data": block.data})
        else:
            blocks.append({"type": block.type})
    return {
        "is_error": result.is_error,
        "structured": result.structured_content is not None,
        "content": blocks,
    }


async def _mcp2_call(client: Client, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = await client.call_tool(name, arguments)
    assert isinstance(result, CallToolResult)
    return _blocks(result)


async def _mcp2_report(url: str, mode: str) -> dict[str, Any]:
    """The mcp1_client.py report, built with the mcp 2.x Client this project locks."""

    async def connect(token: str, run: Any) -> Any:
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx2.AsyncClient(headers=headers) as http:
            async with Client(streamable_http_client(url, http_client=http), mode=mode) as client:
                return await run(client)

    async def main(client: Client) -> dict[str, Any]:
        tools = await client.list_tools()
        hinted = {"ttl_ms", "cache_scope"} & tools.model_fields_set
        info = client.server_info
        assert info is not None
        return {
            "protocol_version": client.protocol_version,
            "server_name": info.name,
            "server_version": info.version,
            "has_tools_capability": client.server_capabilities.tools is not None,
            "tool_count": len(tools.tools),
            "tools_cache_hint": (tools.ttl_ms, tools.cache_scope) if hinted else None,
            "calls": {
                "ping": await _mcp2_call(client, "ping", {}),
                "search": await _mcp2_call(
                    client, "search_collection", {"collection_id": COLLECTION_ID, "query": "intro"}
                ),
                "image": await _mcp2_call(client, "get_blob", {"content_hash": IMAGE_BLOB_HASH}),
                "missing": await _mcp2_call(client, "get_document", {"document_id": "missing"}),
                "bogus": await _mcp2_call(client, "ping", {"bogus": 1}),
            },
        }

    async def whoami(client: Client) -> str:
        block = (await _mcp2_call(client, "whoami", {}))["content"][0]
        collections: list[str] = json.loads(block["text"])["collections"]
        return collections[0]

    report: dict[str, Any] = await connect("key-a", main)
    seen = await asyncio.gather(*(connect(token, whoami) for token in _WHOAMI_TOKENS))
    report["whoami"] = {"tokens": _WHOAMI_TOKENS, "seen": list(seen)}
    return report


@pytest.mark.parametrize(("mode", "negotiated"), [("auto", "2026-07-28"), ("legacy", "2025-11-25")])
async def test_mcp_2x_client_negotiates_by_mode(
    server: ContractServer, mode: str, negotiated: str
) -> None:
    """
    mcp 2.x's Client: `auto` discovers protocol 2026-07-28 (`server/discover`, no handshake);
    `legacy` keeps the initialize handshake at 2025-11-25. Same results either way.
    """
    report = await _mcp2_report(server.url, mode)
    assert report["protocol_version"] == negotiated
    # The tools/list cache hint reaches a 2026-07-28 client only.
    assert report["tools_cache_hint"] == ((3_600_000, "public") if mode == "auto" else None)
    _assert_client_report(report, server)
    first = server.wire[0]
    assert (first.rpc_method, first.status) == (
        ("server/discover", 200) if mode == "auto" else ("initialize", 200)
    )
    # Every request after a handshake (none in auto mode) carries the negotiated version.
    for record in server.wire:
        if record.rpc_method != "initialize":
            assert record.headers.get("mcp-protocol-version") == negotiated, record
