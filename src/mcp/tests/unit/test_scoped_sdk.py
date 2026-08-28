# ====== Code Summary ======
# Unit tests for ScopedSdkProvider/ScopedSdk: fallback resolution, per-token caching/reuse, the
# bounded-cache eviction, and teardown. The real docforge_sdk.AsyncClient is swapped for a tiny
# recording fake so no network client is ever actually opened.

from __future__ import annotations

# ====== Standard Library Imports ======
import asyncio
from typing import cast

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
import libs.scoped_sdk as scoped_sdk_module
from libs.scoped_sdk import ScopedSdk, ScopedSdkProvider
from libs.token_context import incoming_docforge_token


class _FakeAsyncClient:
    """Stand-in for docforge_sdk.AsyncClient that records the token it was built with."""

    def __init__(self, base_url: str, timeout: float, api_token: str = "") -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.api_token = api_token
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _patch_async_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Swap the real docforge_sdk.AsyncClient for the recording fake inside scoped_sdk.py."""
    monkeypatch.setattr(scoped_sdk_module, "AsyncClient", _FakeAsyncClient)


def test_current_falls_back_without_a_context_token() -> None:
    """No context token (stdio, or an HTTP request without a header) -> the fallback client."""
    provider = ScopedSdkProvider("http://api", timeout=5.0, fallback_token="fallback-tok")
    assert cast(_FakeAsyncClient, provider.current).api_token == "fallback-tok"


def test_current_resolves_and_caches_per_token() -> None:
    """A context token resolves to (and reuses) a dedicated client for that token."""
    provider = ScopedSdkProvider("http://api", timeout=5.0, fallback_token="fallback-tok")
    reset = incoming_docforge_token.set("caller-tok")
    try:
        first = provider.current
        second = provider.current
    finally:
        incoming_docforge_token.reset(reset)

    assert cast(_FakeAsyncClient, first).api_token == "caller-tok"
    assert first is second, "the same token must reuse the cached client, not rebuild it"


def test_scoped_sdk_proxy_forwards_to_the_current_client() -> None:
    """ScopedSdk.__getattr__ reads through to the provider's CURRENT client's attribute."""
    provider = ScopedSdkProvider("http://api", timeout=5.0, fallback_token="fallback-tok")
    sdk = ScopedSdk(provider)
    assert sdk.api_token == "fallback-tok"

    reset = incoming_docforge_token.set("caller-tok")
    try:
        assert sdk.api_token == "caller-tok"
    finally:
        incoming_docforge_token.reset(reset)

    # Back outside the context, the same proxy resolves to the fallback again.
    assert sdk.api_token == "fallback-tok"


async def test_aclose_closes_the_fallback_and_every_cached_client() -> None:
    """aclose() tears down the fallback client plus every per-token client ever created."""
    provider = ScopedSdkProvider("http://api", timeout=5.0, fallback_token="fallback-tok")
    reset = incoming_docforge_token.set("caller-tok")
    try:
        cached = provider.current
    finally:
        incoming_docforge_token.reset(reset)

    await provider.aclose()

    assert cast(_FakeAsyncClient, provider._fallback_client).closed
    assert cast(_FakeAsyncClient, cached).closed


async def test_cache_evicts_the_oldest_entry_beyond_the_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Beyond the cache bound, the oldest per-token client is evicted rather than kept forever."""
    monkeypatch.setattr(scoped_sdk_module, "_MAX_CACHED_CLIENTS", 2)
    provider = ScopedSdkProvider("http://api", timeout=5.0, fallback_token="fallback-tok")

    for token in ("t1", "t2", "t3"):
        reset = incoming_docforge_token.set(token)
        try:
            provider.current
        finally:
            incoming_docforge_token.reset(reset)

    assert set(provider._by_token) == {"t2", "t3"}, "t1 must have been evicted first (FIFO)"

    # Let the fire-and-forget eviction close() task (scheduled via asyncio.create_task) run.
    await asyncio.sleep(0)
