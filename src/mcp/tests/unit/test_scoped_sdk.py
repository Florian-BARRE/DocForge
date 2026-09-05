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
from libs.scoped_sdk import MissingBearerTokenError, ScopedSdk, ScopedSdkProvider
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
    """stdio (require_bearer=False) with no context token -> the fallback client."""
    provider = ScopedSdkProvider(
        "http://api", timeout=5.0, fallback_token="fallback-tok", require_bearer=False
    )
    assert cast(_FakeAsyncClient, provider.current).api_token == "fallback-tok"


def test_current_raises_without_a_context_token_when_bearer_is_required() -> None:
    """HTTP mode (require_bearer=True) with no context token -> raise, never the fallback."""
    provider = ScopedSdkProvider(
        "http://api", timeout=5.0, fallback_token="fallback-tok", require_bearer=True
    )
    with pytest.raises(MissingBearerTokenError):
        _ = provider.current


def test_current_resolves_a_context_token_even_when_bearer_is_required() -> None:
    """HTTP mode with a context token still resolves the caller-scoped client normally."""
    provider = ScopedSdkProvider(
        "http://api", timeout=5.0, fallback_token="fallback-tok", require_bearer=True
    )
    reset = incoming_docforge_token.set("caller-tok")
    try:
        assert cast(_FakeAsyncClient, provider.current).api_token == "caller-tok"
    finally:
        incoming_docforge_token.reset(reset)


def test_current_resolves_and_caches_per_token() -> None:
    """A context token resolves to (and reuses) a dedicated client for that token."""
    provider = ScopedSdkProvider(
        "http://api", timeout=5.0, fallback_token="fallback-tok", require_bearer=False
    )
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
    provider = ScopedSdkProvider(
        "http://api", timeout=5.0, fallback_token="fallback-tok", require_bearer=False
    )
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
    provider = ScopedSdkProvider(
        "http://api", timeout=5.0, fallback_token="fallback-tok", require_bearer=False
    )
    reset = incoming_docforge_token.set("caller-tok")
    try:
        cached = provider.current
    finally:
        incoming_docforge_token.reset(reset)

    await provider.aclose()

    assert cast(_FakeAsyncClient, provider._fallback_client).closed
    assert cast(_FakeAsyncClient, cached).closed


async def test_cache_evicts_the_least_recently_used_entry_beyond_the_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Beyond the cache bound, the least-recently-used per-token client is evicted."""
    monkeypatch.setattr(scoped_sdk_module, "_MAX_CACHED_CLIENTS", 2)
    provider = ScopedSdkProvider(
        "http://api", timeout=5.0, fallback_token="fallback-tok", require_bearer=False
    )

    for token in ("t1", "t2", "t3"):
        reset = incoming_docforge_token.set(token)
        try:
            provider.current
        finally:
            incoming_docforge_token.reset(reset)

    assert set(provider._by_token) == {"t2", "t3"}, "t1 must have been evicted (never re-touched)"

    # Let the tracked eviction close() task run to completion.
    await asyncio.gather(*provider._pending_closes)


async def test_cache_touching_the_oldest_entry_saves_it_from_eviction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cache hit on the oldest entry marks it most-recently-used, so a DIFFERENT entry is
    evicted next — this is what distinguishes LRU from FIFO."""
    monkeypatch.setattr(scoped_sdk_module, "_MAX_CACHED_CLIENTS", 2)
    provider = ScopedSdkProvider(
        "http://api", timeout=5.0, fallback_token="fallback-tok", require_bearer=False
    )

    for token in ("t1", "t2"):
        reset = incoming_docforge_token.set(token)
        try:
            provider.current
        finally:
            incoming_docforge_token.reset(reset)

    # Touch t1 again (a cache hit) before introducing a third, distinct token: this must move
    # t1 to the most-recently-used end, so a FIFO implementation (which would evict t1) and an
    # LRU implementation (which evicts t2) disagree here.
    for token in ("t1", "t3"):
        reset = incoming_docforge_token.set(token)
        try:
            provider.current
        finally:
            incoming_docforge_token.reset(reset)

    assert set(provider._by_token) == {
        "t1",
        "t3",
    }, "t2 must be evicted, not t1, since t1 was re-touched before t3 was added"

    await asyncio.gather(*provider._pending_closes)


async def test_cache_eviction_closes_the_evicted_client_via_a_tracked_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The evicted client's close() is awaited via a task held in `_pending_closes`, not an
    unreferenced fire-and-forget task, and it actually completes."""
    monkeypatch.setattr(scoped_sdk_module, "_MAX_CACHED_CLIENTS", 1)
    provider = ScopedSdkProvider(
        "http://api", timeout=5.0, fallback_token="fallback-tok", require_bearer=False
    )

    reset = incoming_docforge_token.set("t1")
    try:
        evicted = provider.current
    finally:
        incoming_docforge_token.reset(reset)

    reset = incoming_docforge_token.set("t2")
    try:
        provider.current
    finally:
        incoming_docforge_token.reset(reset)

    assert provider._pending_closes, "the eviction close task must be tracked, not fire-and-forget"
    await asyncio.gather(*provider._pending_closes)

    assert cast(_FakeAsyncClient, evicted).closed
    assert not provider._pending_closes, "the done-callback must remove the task once finished"


async def test_cache_eviction_close_error_is_logged_and_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A close() failure on an evicted client is logged, not raised into the caller's request
    path, and does not leave the task dangling."""

    class _FailingAsyncClient(_FakeAsyncClient):
        async def aclose(self) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr(scoped_sdk_module, "AsyncClient", _FailingAsyncClient)
    monkeypatch.setattr(scoped_sdk_module, "_MAX_CACHED_CLIENTS", 1)
    provider = ScopedSdkProvider(
        "http://api", timeout=5.0, fallback_token="fallback-tok", require_bearer=False
    )

    for token in ("t1", "t2"):
        reset = incoming_docforge_token.set(token)
        try:
            provider.current
        finally:
            incoming_docforge_token.reset(reset)

    (pending_task,) = tuple(provider._pending_closes)
    logged_errors: list[str] = []
    monkeypatch.setattr(provider.logger, "error", lambda msg: logged_errors.append(msg))

    # Awaiting a task's own reference does not re-raise past its done-callback; the callback
    # already ran (or runs here) without propagating into this test.
    await asyncio.gather(pending_task, return_exceptions=True)

    assert logged_errors, "the close failure must be logged"
    assert not provider._pending_closes, "the task must be removed from tracking even on failure"
