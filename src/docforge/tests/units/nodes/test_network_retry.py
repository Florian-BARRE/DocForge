"""NetworkRetry bounded retry — the shared transient-only loop of ocr/llm/gotenberg/structgen/pp_structure.

Pins the attempt-count contract so it cannot drift from the bespoke embed/vlm loops: ``max_retries``
counts retries BEYOND the initial call, so a transient operation is tried exactly ``1 + max_retries``
times before the error re-raises to the graph's own escalation. The same (0→1, 1→2, 2→3) table the
embed guard (``test_embed_stage.py``) and the vlm guard (``test_vlm_retry.py``) assert — the three
families must agree. ``asyncio.sleep`` is stubbed so the backoff costs no wall-clock time.
"""

from unittest.mock import AsyncMock

import httpx
import pytest

from shared_libs.pipelines.nodes import retry as retry_module
from shared_libs.pipelines.nodes.retry import NetworkRetry


@pytest.mark.parametrize(("max_retries", "expected_attempts"), [(0, 1), (1, 2), (2, 3)])
async def test_max_retries_counts_retries_beyond_the_initial_call(
    monkeypatch, max_retries: int, expected_attempts: int
) -> None:
    # Contract: total attempts = 1 + max_retries — identical to the embed and vlm hand-loops.
    monkeypatch.setattr(retry_module.asyncio, "sleep", AsyncMock())
    operation = AsyncMock(side_effect=httpx.ConnectError("down"))

    with pytest.raises(httpx.ConnectError):
        await NetworkRetry.run(
            operation, max_retries=max_retries, retry_backoff_seconds=0.0, label="test"
        )

    assert operation.await_count == expected_attempts


async def test_non_transient_error_reraises_immediately_without_retry(monkeypatch) -> None:
    sleep = AsyncMock()
    monkeypatch.setattr(retry_module.asyncio, "sleep", sleep)
    # A ValueError is not in the transient set (a 4xx/auth-style permanent error) — never retried.
    operation = AsyncMock(side_effect=ValueError("bad request"))

    with pytest.raises(ValueError):
        await NetworkRetry.run(operation, max_retries=5, retry_backoff_seconds=0.0, label="test")

    assert operation.await_count == 1
    sleep.assert_not_awaited()
