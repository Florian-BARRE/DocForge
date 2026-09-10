"""The shared HttpClientPool — the connection-reuse fix for the raw-httpx nodes.

These pin the one behaviour the whole fix exists for: a node that calls its endpoint more than once
(successive batches, or retries) constructs its httpx.AsyncClient ONCE and reuses the kept-alive
connection, instead of paying a fresh socket + TLS handshake per call. Everything is offline: the
real ``httpx.AsyncClient`` is monkeypatched with a stand-in that counts its own constructions.

The autouse ``_reset_http_pool`` fixture (conftest.py) clears the process-wide pool before each
test, so the reuse asserted here is strictly WITHIN a single test.
"""

import asyncio

import httpx
import pytest

from shared_libs.pipelines.nodes.embed.bge_server.core import (
    EmbedBgeServerConfig,
    EmbedBgeServerNode,
)
from shared_libs.pipelines.nodes.http_pool import HttpClientPool


class _FakeResponse:
    """A stand-in httpx.Response carrying a canned JSON body."""

    def __init__(self, payload: object) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._payload


def _counting_async_client(*, constructions: list[dict], payload: object):
    """An httpx.AsyncClient stand-in that appends its construction kwargs to a shared list."""

    class _Client:
        is_closed = False

        def __init__(self, *args: object, **kwargs: object) -> None:
            constructions.append(kwargs)

        async def post(self, *args: object, **kwargs: object) -> _FakeResponse:
            return _FakeResponse(payload)

    return _Client


# ==================== node-level reuse (the point of the fix) ====================


def test_bge_node_reuses_one_client_across_two_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two embed calls on the bge_server node build the httpx client ONCE — connection reuse."""
    constructions: list[dict] = []
    monkeypatch.setattr(
        httpx, "AsyncClient", _counting_async_client(constructions=constructions, payload=[[0.1]])
    )
    node = EmbedBgeServerNode(
        id="e", config=EmbedBgeServerConfig(base_url="http://bge_server:80", api_key="tok")
    )

    async def _two_calls() -> None:
        # Two successive batches against the same endpoint — must share the one pooled client.
        await node._embed_dense(["a"])
        await node._embed_dense(["b"])

    asyncio.run(_two_calls())
    assert len(constructions) == 1
    # The bearer rides per-request, never at construction — so it never fragments the pool key.
    assert constructions[0].get("auth") is None


# ==================== pool semantics ====================


def test_same_identity_returns_the_same_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two get() calls with identical connection identity return the very same client instance."""
    constructions: list[dict] = []
    monkeypatch.setattr(
        httpx, "AsyncClient", _counting_async_client(constructions=constructions, payload=None)
    )
    first = HttpClientPool.get(base_url="http://x:80", timeout=30.0)
    second = HttpClientPool.get(base_url="http://x:80", timeout=30.0)
    assert first is second
    assert len(constructions) == 1


def test_distinct_identity_gets_distinct_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    """A different base_url, timeout, or auth each key a separate pooled client."""
    constructions: list[dict] = []
    monkeypatch.setattr(
        httpx, "AsyncClient", _counting_async_client(constructions=constructions, payload=None)
    )
    HttpClientPool.get(base_url="http://x:80", timeout=30.0)
    HttpClientPool.get(base_url="http://y:80", timeout=30.0)  # different endpoint
    HttpClientPool.get(base_url="http://x:80", timeout=60.0)  # different timeout
    HttpClientPool.get(base_url="http://x:80", timeout=30.0, auth=httpx.BasicAuth("u", "p"))
    assert len(constructions) == 4


def test_a_closed_client_is_recreated(monkeypatch: pytest.MonkeyPatch) -> None:
    """A client found closed (e.g. cached on a now-closed loop) is transparently recreated."""

    class _ClosableClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.is_closed = False

        async def post(self, *args: object, **kwargs: object) -> _FakeResponse:
            return _FakeResponse(None)

    monkeypatch.setattr(httpx, "AsyncClient", _ClosableClient)
    first = HttpClientPool.get(base_url="http://x:80", timeout=30.0)
    first.is_closed = True
    second = HttpClientPool.get(base_url="http://x:80", timeout=30.0)
    assert first is not second


def test_shutdown_closes_and_clears(monkeypatch: pytest.MonkeyPatch) -> None:
    """shutdown() aclose()s every pooled client and empties the registry."""
    closed: list[bool] = []

    class _ClosableClient:
        is_closed = False

        def __init__(self, *args: object, **kwargs: object) -> None: ...

        async def aclose(self) -> None:
            closed.append(True)

    monkeypatch.setattr(httpx, "AsyncClient", _ClosableClient)
    HttpClientPool.get(base_url="http://x:80", timeout=30.0)
    asyncio.run(HttpClientPool.shutdown())
    assert closed == [True]
    # The registry is empty afterwards — the next get() builds a fresh client.
    assert HttpClientPool._clients == {}
