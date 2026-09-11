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

import httpx
import openai
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


# ==================== restart resilience (arun() self-heal) ====================

_CHAT_KWARGS = dict(
    base_url="http://x/v1",
    api_key="k",
    model="m",
    temperature=0.0,
    max_tokens=None,
    timeout=30.0,
    seed=None,
    max_retries=0,
)


def _connect_error() -> openai.APIConnectionError:
    """An openai APIConnectionError caused by a connect-phase httpx error (no byte sent → replayable)."""
    error = openai.APIConnectionError(request=httpx.Request("POST", "http://x/v1"))
    error.__cause__ = httpx.ConnectError("All connection attempts failed")
    return error


class _Binding:
    """Stand-in for a with_config RunnableBinding — its ``.bound`` is the pooled client (vlm/structgen)."""

    def __init__(self, bound: object) -> None:
        self.bound = bound


def test_arun_evicts_recreates_and_retries_once_on_connect_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dead-socket connect error evicts the pooled client, recreates it, and replays the op once."""
    constructions: list[dict] = []
    monkeypatch.setattr(client_pool_module, "ChatOpenAI", _counting_chat(constructions))
    seen: list = []

    async def _op(model: object) -> str:
        seen.append(model)
        if len(seen) == 1:
            raise _connect_error()
        return "ok"

    result = asyncio.run(
        LangChainClientPool.arun(lambda: LangChainClientPool.chat(**_CHAT_KWARGS), _op)
    )

    assert result == "ok"
    assert len(seen) == 2  # one failed attempt + one retry
    assert seen[0] is not seen[1]  # the retry ran on a FRESH client, not the dead one
    assert seen[0].root_async_client.close_calls == 1  # the dead client's transport was closed
    assert len(constructions) == 2  # original + recreated
    assert (
        LangChainClientPool.chat(**_CHAT_KWARGS) is seen[1]
    )  # the healthy fresh client stays pooled


def test_arun_evicts_the_pooled_client_behind_a_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    """The evict unwraps a with_config binding to reach and drop the real pooled client."""
    constructions: list[dict] = []
    monkeypatch.setattr(client_pool_module, "ChatOpenAI", _counting_chat(constructions))
    seen: list = []

    async def _op(resource: object) -> str:
        seen.append(resource)
        if len(seen) == 1:
            raise _connect_error()
        return "ok"

    result = asyncio.run(
        LangChainClientPool.arun(lambda: _Binding(LangChainClientPool.chat(**_CHAT_KWARGS)), _op)
    )

    assert result == "ok"
    assert seen[0].bound is not seen[1].bound  # a fresh underlying client backed the retry
    assert seen[0].bound.root_async_client.close_calls == 1  # the dead pooled client was closed
    assert len(constructions) == 2


def test_arun_does_not_retry_a_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """A read/connect timeout may follow a sent request — re-raised, never replayed."""
    monkeypatch.setattr(client_pool_module, "ChatOpenAI", _counting_chat([]))
    seen: list = []

    async def _op(model: object) -> str:
        seen.append(model)
        raise openai.APITimeoutError(request=httpx.Request("POST", "http://x/v1"))

    with pytest.raises(openai.APITimeoutError):
        asyncio.run(LangChainClientPool.arun(lambda: LangChainClientPool.chat(**_CHAT_KWARGS), _op))

    assert len(seen) == 1  # NOT replayed
    assert LangChainClientPool.chat(**_CHAT_KWARGS) is seen[0]  # the client was not evicted


def test_arun_does_not_retry_a_non_connect_cause(monkeypatch: pytest.MonkeyPatch) -> None:
    """An APIConnectionError wrapping a read/write error (bytes may have been sent) is not replayed."""
    monkeypatch.setattr(client_pool_module, "ChatOpenAI", _counting_chat([]))
    seen: list = []

    async def _op(model: object) -> str:
        seen.append(model)
        error = openai.APIConnectionError(request=httpx.Request("POST", "http://x/v1"))
        error.__cause__ = httpx.ReadError("response half-read")
        raise error

    with pytest.raises(openai.APIConnectionError):
        asyncio.run(LangChainClientPool.arun(lambda: LangChainClientPool.chat(**_CHAT_KWARGS), _op))

    assert len(seen) == 1  # NOT replayed — only a connect-phase failure is idempotency-safe


def test_arun_reraises_when_the_fresh_client_also_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """The endpoint is still down: after one evict+retry the connect error propagates (no loop)."""
    monkeypatch.setattr(client_pool_module, "ChatOpenAI", _counting_chat([]))
    seen: list = []

    async def _op(model: object) -> str:
        seen.append(model)
        raise _connect_error()

    with pytest.raises(openai.APIConnectionError):
        asyncio.run(LangChainClientPool.arun(lambda: LangChainClientPool.chat(**_CHAT_KWARGS), _op))

    assert len(seen) == 2  # exactly one retry, then give up
