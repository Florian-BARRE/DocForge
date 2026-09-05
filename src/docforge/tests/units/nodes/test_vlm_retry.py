"""BaseVlmNode bounded retry — transient-only, cost-sober, BELOW the graph's escalation.

A VLM call is PAID, so the retry is narrow: a timeout/connection/429/5xx is transient and repeated
up to ``max_retries`` times; a 4xx (auth/bad request) or any non-transient error re-raises at once
(no wasted calls); after the retries are exhausted the error re-raises so the existing
ScoreBelow/OnFailure chaining to the next provider still takes over. ``_describe`` is mocked;
``asyncio.sleep`` is stubbed so the backoff costs no wall-clock time.
"""

from unittest.mock import AsyncMock

import httpx
import pytest

from shared_libs.pipelines.nodes.openai_compat import UsageAccumulator
from shared_libs.pipelines.nodes.vlm.base import BaseVlmConfig, BaseVlmNode
from shared_libs.pipelines.nodes.vlm.base import node as node_module
from shared_libs.public_models import FigureItem


class _FakeVlm(BaseVlmNode):
    """A bare VLM node whose ``_describe`` each test replaces — never registered nor networked."""

    KIND = "test_vlm_retry_fake"
    NAME = "F"
    SUMMARY = "test"
    Config = BaseVlmConfig

    async def _describe(
        self,
        image: bytes,
        context: str,
        system_prompt: str,
        usage_sink: UsageAccumulator | None = None,
    ) -> tuple[str, float]:
        raise NotImplementedError  # replaced per test


def _node(max_retries: int) -> _FakeVlm:
    return _FakeVlm("vlm", BaseVlmConfig(max_retries=max_retries, retry_backoff_seconds=0.01))


def _data() -> object:
    from shared_libs.pipelines.nodes.vlm.base.io import VlmConsumes  # noqa: PLC0415

    return VlmConsumes(figure=FigureItem(block_id="b", image=b"img", read_text=""))


async def test_transient_twice_then_success_returns_within_retries(monkeypatch) -> None:
    monkeypatch.setattr(node_module.asyncio, "sleep", AsyncMock())
    node = _node(max_retries=3)
    describe = AsyncMock(
        side_effect=[httpx.ConnectError("blip"), httpx.ConnectError("blip"), ("described", 1.0)]
    )
    monkeypatch.setattr(node, "_describe", describe)

    result = await node.run(_data())

    assert result.entry.description == "described"
    assert describe.await_count == 3  # 2 transient failures + 1 success


async def test_always_transient_reraises_after_exactly_max_retries_plus_one(monkeypatch) -> None:
    monkeypatch.setattr(node_module.asyncio, "sleep", AsyncMock())
    node = _node(max_retries=2)
    describe = AsyncMock(side_effect=httpx.ConnectError("down"))
    monkeypatch.setattr(node, "_describe", describe)

    with pytest.raises(httpx.ConnectError):
        await node.run(_data())

    assert describe.await_count == 3  # max_retries (2) + the initial attempt


async def test_non_transient_error_reraises_immediately_without_retry(monkeypatch) -> None:
    sleep = AsyncMock()
    monkeypatch.setattr(node_module.asyncio, "sleep", sleep)
    node = _node(max_retries=5)
    # A ValueError is not in the transient set (a 4xx/auth-style permanent error) — never retried.
    describe = AsyncMock(side_effect=ValueError("bad request"))
    monkeypatch.setattr(node, "_describe", describe)

    with pytest.raises(ValueError):
        await node.run(_data())

    assert describe.await_count == 1
    sleep.assert_not_awaited()
