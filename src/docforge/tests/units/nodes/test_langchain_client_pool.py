"""The shared LangChainClientPool — the connection-reuse fix for the hosted LLM/VLM/embed nodes.

These pin the one behaviour the whole fix exists for: a node that calls its endpoint more than once
(the metagen/contextualize/enrich per-item ForEach, a retry loop) constructs its ChatOpenAI /
OpenAIEmbeddings — each of which owns an openai.AsyncOpenAI connection pool + TLS — ONCE and reuses
it, instead of opening a fresh client per call. Critically, usage attribution still happens PER CALL:
a UsageAccumulator is overlaid as a ``with_config`` callback binding over the ONE shared client, so
two calls with two different sinks never cross-contaminate while both reuse the same connection.

The autouse ``_reset_client_pools`` fixture (conftest.py) clears the process-wide pools before each
test, so the reuse asserted here is strictly WITHIN a single test.
"""

import asyncio

import pytest

from shared_libs.pipelines.nodes.openai_compat import (
    LangChainClientPool,
    OpenAICompatConfig,
    OpenAICompatHelpers,
    UsageAccumulator,
)
from shared_libs.pipelines.nodes.openai_compat import client_pool as client_pool_module


def _cfg() -> OpenAICompatConfig:
    return OpenAICompatConfig(base_url="http://endpoint/v1", api_key="k", model="m")


# ==================== factory-level reuse + per-call usage (the point of the fix) ====================


def test_two_chat_calls_share_one_client_and_attribute_usage_per_call() -> None:
    """Two chat() calls (≥2 ForEach items) build ONE underlying client; each sink stays its own.

    The real ChatOpenAI is constructed (offline — no network until invoke), so we can prove both: the
    memoized client is the very same instance behind both per-call bindings (one construction), and
    each binding carries ONLY its own UsageAccumulator (no cross-contamination between concurrent
    items).
    """
    sink_a = UsageAccumulator("m")
    sink_b = UsageAccumulator("m")
    bound_a = OpenAICompatHelpers.chat(_cfg(), usage_sink=sink_a)
    bound_b = OpenAICompatHelpers.chat(_cfg(), usage_sink=sink_b)

    # One shared underlying client behind both per-call bindings — the connection is reused.
    assert bound_a.bound is bound_b.bound
    # Each invocation attributes to its OWN sink only — the bindings never cross-contaminate.
    assert bound_a.config.get("callbacks") == [sink_a]
    assert bound_b.config.get("callbacks") == [sink_b]


def test_embeddings_calls_share_one_client() -> None:
    """Two embeddings() calls on the same endpoint return the very same pooled client."""
    first = OpenAICompatHelpers.embeddings(_cfg())
    second = OpenAICompatHelpers.embeddings(_cfg())
    assert first is second


# ==================== pool semantics (offline counting stand-in) ====================


class _FakeTransport:
    """Stand-in openai.AsyncOpenAI — a closable transport whose closed-state is togglable."""

    def __init__(self) -> None:
        self._closed = False
        self.close_calls = 0

    def is_closed(self) -> bool:
        return self._closed

    async def close(self) -> None:
        self.close_calls += 1
        self._closed = True


def _counting_chat(constructions: list[dict]):
    """A ChatOpenAI stand-in appending its construction kwargs to a shared list."""

    class _Chat:
        def __init__(self, **kwargs: object) -> None:
            constructions.append(kwargs)
            self.root_async_client = _FakeTransport()

    return _Chat


def test_same_identity_returns_the_same_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two chat() pool calls with identical construction identity return one client instance."""
    constructions: list[dict] = []
    monkeypatch.setattr(client_pool_module, "ChatOpenAI", _counting_chat(constructions))
    first = LangChainClientPool.chat(
        base_url="http://x/v1",
        api_key="k",
        model="m",
        temperature=0.0,
        max_tokens=None,
        timeout=30.0,
        seed=None,
        max_retries=0,
    )
    second = LangChainClientPool.chat(
        base_url="http://x/v1",
        api_key="k",
        model="m",
        temperature=0.0,
        max_tokens=None,
        timeout=30.0,
        seed=None,
        max_retries=0,
    )
    assert first is second
    assert len(constructions) == 1


def test_distinct_identity_gets_distinct_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    """A different endpoint, credential, model, or param each key a separate pooled client."""
    constructions: list[dict] = []
    monkeypatch.setattr(client_pool_module, "ChatOpenAI", _counting_chat(constructions))
    base = dict(
        base_url="http://x/v1",
        api_key="k",
        model="m",
        temperature=0.0,
        max_tokens=None,
        timeout=30.0,
        seed=None,
        max_retries=0,
    )
    LangChainClientPool.chat(**base)
    LangChainClientPool.chat(**{**base, "base_url": "http://y/v1"})  # different endpoint
    LangChainClientPool.chat(**{**base, "api_key": "k2"})  # different credential
    LangChainClientPool.chat(**{**base, "temperature": 0.7})  # different sampling
    assert len(constructions) == 4


def test_a_closed_client_is_recreated(monkeypatch: pytest.MonkeyPatch) -> None:
    """A client whose transport is found closed (cached on a now-closed loop) is recreated."""
    constructions: list[dict] = []
    monkeypatch.setattr(client_pool_module, "ChatOpenAI", _counting_chat(constructions))
    args = dict(
        base_url="http://x/v1",
        api_key="k",
        model="m",
        temperature=0.0,
        max_tokens=None,
        timeout=30.0,
        seed=None,
        max_retries=0,
    )
    first = LangChainClientPool.chat(**args)
    first.root_async_client._closed = True  # simulate a dropped loop/transport
    second = LangChainClientPool.chat(**args)
    assert first is not second
    assert len(constructions) == 2


def test_shutdown_closes_transports_and_clears(monkeypatch: pytest.MonkeyPatch) -> None:
    """shutdown() closes every pooled client's transport and empties both registries."""
    monkeypatch.setattr(client_pool_module, "ChatOpenAI", _counting_chat([]))
    client = LangChainClientPool.chat(
        base_url="http://x/v1",
        api_key="k",
        model="m",
        temperature=0.0,
        max_tokens=None,
        timeout=30.0,
        seed=None,
        max_retries=0,
    )
    transport = client.root_async_client
    asyncio.run(LangChainClientPool.shutdown())
    assert transport.close_calls == 1
    assert LangChainClientPool._chat_clients == {}
    assert LangChainClientPool._embed_clients == {}
