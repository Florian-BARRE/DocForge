"""BaseVlmNode usage attribution — the OWN retry loop sums EVERY paid attempt, not just the last.

The VLM node runs its own transient-retry loop (below the graph's escalation), so a paid attempt that
billed then failed/retried must still be attributed. The node threads ONE ``UsageAccumulator`` across
the whole loop and stamps its summed total on the output. These tests drive ``_describe`` with a stub
that records into the passed sink (standing in for the live ``on_llm_end`` callback), proving:
a bill-then-fail-then-succeed run stamps the SUMMED usage; a single success stamps that one attempt's
usage (unchanged); a usage-less provider stamps None (a free provider stays free).
"""

from unittest.mock import AsyncMock

import httpx

from shared_libs.pipelines.nodes.openai_compat import UsageAccumulator
from shared_libs.pipelines.nodes.vlm.base import BaseVlmConfig, BaseVlmNode
from shared_libs.pipelines.nodes.vlm.base import node as node_module
from shared_libs.pipelines.nodes.vlm.base.io import VlmConsumes
from shared_libs.public_models import FigureItem


class _FakeVlmConfig(BaseVlmConfig):
    """A base VLM config plus a ``model`` id (the concrete providers carry one; the base does not)."""

    model: str = "m"


class _FakeVlm(BaseVlmNode):
    """A bare VLM node whose ``_describe`` each test replaces — never registered nor networked."""

    KIND = "test_vlm_usage_fake"
    NAME = "F"
    SUMMARY = "test"
    Config = _FakeVlmConfig

    async def _describe(
        self,
        image: bytes,
        context: str,
        system_prompt: str,
        usage_sink: UsageAccumulator | None = None,
    ) -> tuple[str, float]:
        raise NotImplementedError  # replaced per test


def _node(max_retries: int = 3) -> _FakeVlm:
    return _FakeVlm(
        "vlm", _FakeVlmConfig(model="m", max_retries=max_retries, retry_backoff_seconds=0.01)
    )


def _data() -> VlmConsumes:
    return VlmConsumes(figure=FigureItem(block_id="b", image=b"img", read_text=""))


async def test_bills_then_fails_then_succeeds_stamps_the_summed_usage(monkeypatch) -> None:
    """First attempt bills then fails transiently, second succeeds — the SUMMED usage is stamped."""
    monkeypatch.setattr(node_module.asyncio, "sleep", AsyncMock())
    node = _node(max_retries=3)
    attempts: list[int] = []

    async def describe(
        image: bytes,
        context: str,
        system_prompt: str,
        usage_sink: UsageAccumulator | None = None,
    ) -> tuple[str, float]:
        # Each attempt "bills" (the live on_llm_end fold, simulated) into the SHARED sink.
        assert usage_sink is not None
        usage_sink.record(100, 10)
        attempts.append(1)
        if len(attempts) == 1:  # first attempt billed, then failed transiently → retried
            raise httpx.ConnectError("blip")
        return "described", 1.0

    monkeypatch.setattr(node, "_describe", describe)

    result = await node.run(_data())

    assert result.entry.description == "described"
    assert len(attempts) == 2
    assert result._usage is not None
    assert result._usage.model == "m"
    assert result._usage.prompt_tokens == 200  # summed across both attempts, not just the last
    assert result._usage.completion_tokens == 20


async def test_single_successful_attempt_stamps_that_attempts_usage(monkeypatch) -> None:
    """One successful attempt stamps exactly that attempt's usage (behaviour unchanged)."""
    monkeypatch.setattr(node_module.asyncio, "sleep", AsyncMock())
    node = _node()

    async def describe(
        image: bytes,
        context: str,
        system_prompt: str,
        usage_sink: UsageAccumulator | None = None,
    ) -> tuple[str, float]:
        assert usage_sink is not None
        usage_sink.record(42, 7)
        return "described", 1.0

    monkeypatch.setattr(node, "_describe", describe)

    result = await node.run(_data())

    assert result._usage is not None
    assert result._usage.prompt_tokens == 42
    assert result._usage.completion_tokens == 7


async def test_usageless_provider_stamps_none(monkeypatch) -> None:
    """A provider that never records usage leaves the output usage None (a free provider stays free)."""
    monkeypatch.setattr(node_module.asyncio, "sleep", AsyncMock())
    node = _node()

    async def describe(
        image: bytes,
        context: str,
        system_prompt: str,
        usage_sink: UsageAccumulator | None = None,
    ) -> tuple[str, float]:
        return "described", 1.0  # never touches usage_sink

    monkeypatch.setattr(node, "_describe", describe)

    result = await node.run(_data())

    assert result.entry.description == "described"
    assert result._usage is None
