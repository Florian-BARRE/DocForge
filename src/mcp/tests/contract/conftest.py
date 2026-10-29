# ====== Code Summary ======
# Fixtures of the MCP compatibility-contract tests: the REAL server (build_mcp + build_http_app,
# wired like entrypoint.py's HTTP mode) served by uvicorn on an ephemeral localhost port, over a
# fake DocForge API (httpx.MockTransport behind every per-token docforge_sdk client). A recorder
# wraps the app to keep each wire request (headers, JSON-RPC method, status) so a test can assert
# the exact handshake a client performed.

from __future__ import annotations

# ====== Standard Library Imports ======
import asyncio
import json
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, cast

# ====== Third-Party Library Imports ======
import httpx
import pytest
import uvicorn
from docforge_sdk import AsyncClient
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# ====== Internal Project Imports ======
import libs.scoped_sdk as scoped_sdk_module
from libs.path_guard import PathGuard
from libs.scoped_sdk import ScopedSdk, ScopedSdkProvider
from libs.server import build_http_app, build_mcp

# A 1x1 transparent PNG: what the fake API serves for an image blob.
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)
IMAGE_BLOB_HASH = "a" * 64
COLLECTION_ID = "11111111-1111-1111-1111-111111111111"

_SEARCH_RESPONSE: dict[str, Any] = {
    "query": "intro",
    "hits": [{"chunk_id": "c1", "document_id": "d1", "page_number": 5, "text": "Hello world."}],
}


@dataclass
class WireRecord:
    """One HTTP request as the server received it, and the status it answered."""

    headers: dict[str, str]
    rpc_method: str | None
    status: int | None = None


@dataclass
class FakeDocForgeApi:
    """The fake DocForge REST API every SDK client of the server talks to."""

    # (Authorization header, path) of every API call, in arrival order.
    calls: list[tuple[str, str]] = field(default_factory=list)

    async def handle(self, request: httpx.Request) -> httpx.Response:
        """Answer one SDK request; any route not listed here is a DocForge 404."""
        auth = request.headers.get("authorization", "")
        path = request.url.path
        self.calls.append((auth, path))
        if path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if path == "/api/v1/auth/whoami":
            # Slow and token-dependent, so concurrent callers overlap and each sees its own key.
            await asyncio.sleep(0.2)
            token = auth.removeprefix("Bearer ")
            return httpx.Response(
                200,
                json={
                    "authenticated": True,
                    "root": False,
                    "capabilities": [],
                    "collections": [token],
                },
            )
        if path == f"/api/v1/blobs/{IMAGE_BLOB_HASH}":
            return httpx.Response(200, content=PNG_BYTES, headers={"content-type": "image/png"})
        if path == f"/api/v1/collections/{COLLECTION_ID}/search":
            return httpx.Response(200, json=_SEARCH_RESPONSE)
        if path == "/api/v1/documents":
            return httpx.Response(202, json={"document_id": "d-new", "job_id": "j-new"})
        return httpx.Response(404, json={"detail": "nope"})


class _WireRecorder:
    """Raw ASGI wrapper (outermost, test-only) that records each request and its status."""

    def __init__(self, app: ASGIApp, records: list[WireRecord]) -> None:
        self._app = app
        self._records = records

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        # Buffer the body to read the JSON-RPC method, then replay it to the app unchanged.
        chunks: list[bytes] = []
        while True:
            message = await receive()
            chunks.append(message.get("body", b""))
            if not message.get("more_body"):
                break
        body = b"".join(chunks)
        record = WireRecord(
            headers={k.decode("latin-1"): v.decode("latin-1") for k, v in scope["headers"]},
            rpc_method=_rpc_method(body),
        )
        self._records.append(record)
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if replayed:
                return await receive()
            replayed = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def recording_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                record.status = message["status"]
            await send(message)

        await self._app(scope, replay, recording_send)


def _rpc_method(body: bytes) -> str | None:
    """The JSON-RPC method of a request body (None for a response, a batch or no JSON)."""
    try:
        payload = json.loads(body)
    except ValueError:
        return None
    return payload.get("method") if isinstance(payload, dict) else None


class _ContractConfig:
    """The McpConfig attributes build_http_app reads, at their production defaults."""

    MCP_HOST = "127.0.0.1"
    MCP_PORT = 0
    MCP_HTTP_PATH = "/mcp"
    MCP_MAX_INLINE_UPLOAD_BYTES = 100 * 1024 * 1024


@dataclass
class ContractServer:
    """The running server: its MCP endpoint, the fake API behind it, and the wire log."""

    url: str
    api: FakeDocForgeApi
    wire: list[WireRecord]
    # The SDK client class wired to the fake API, patched into scoped_sdk for each test.
    client_class: type[AsyncClient]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return cast(int, sock.getsockname()[1])


def _mocked_client_class(mock: httpx.MockTransport) -> type[AsyncClient]:
    """A docforge_sdk.AsyncClient subclass whose HTTP traffic goes to the fake API."""

    class _MockedAsyncClient(AsyncClient):
        """A real docforge_sdk client whose HTTP traffic goes to the fake API."""

        def __init__(self, base_url: str, timeout: float = 30.0, api_token: str = "") -> None:
            super().__init__(base_url, timeout=timeout, api_token=api_token)
            # No public seam: swaps the private AsyncTransport._client of docforge_sdk 0.31.3.
            transport = cast(Any, self._transport)
            transport._client = httpx.AsyncClient(
                transport=mock, headers=transport._headers, timeout=timeout
            )

    return _MockedAsyncClient


@pytest.fixture(scope="session")
def contract_server() -> Iterator[ContractServer]:
    """
    Serve the real streamable-HTTP app, wired like entrypoint.py's HTTP mode, on localhost.

    scoped_sdk's AsyncClient is patched only while the provider is built (its fallback client);
    the per-token clients, built lazily during a request, get the patch from the ``server``
    fixture, so it never outlives a contract test.

    Yields:
        ContractServer: The endpoint URL (``http://127.0.0.1:<port>/mcp``) and the fakes.
    """
    api = FakeDocForgeApi()
    wire: list[WireRecord] = []
    client_class = _mocked_client_class(httpx.MockTransport(api.handle))

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(scoped_sdk_module, "AsyncClient", client_class)
        provider = ScopedSdkProvider(
            "http://docforge.test", timeout=10.0, fallback_token="", require_bearer=True
        )
    sdk = cast(AsyncClient, ScopedSdk(provider))
    mcp = build_mcp(sdk, PathGuard(confine=True, inbox_dir=None))
    app = _WireRecorder(build_http_app(mcp, _ContractConfig), wire)  # type: ignore[arg-type]

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError("the contract MCP server did not start")
        time.sleep(0.05)
    try:
        yield ContractServer(
            url=f"http://127.0.0.1:{port}/mcp", api=api, wire=wire, client_class=client_class
        )
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture
def server(contract_server: ContractServer, monkeypatch: pytest.MonkeyPatch) -> ContractServer:
    """The session server, its SDK clients on the fake API and its logs emptied, for this test."""
    monkeypatch.setattr(scoped_sdk_module, "AsyncClient", contract_server.client_class)
    contract_server.wire.clear()
    contract_server.api.calls.clear()
    return contract_server
