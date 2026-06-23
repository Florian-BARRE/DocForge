# ====== Code Summary ======
# Unit tests for QueueIntrospector — read-only arq queue introspection over a fake Redis.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from libs.observability.queue import ARQ_QUEUE_KEY, QueueIntrospector


class FakeRedis:
    """Minimal async Redis double covering the introspector's read-only calls."""

    def __init__(self, *, zcard: int = 0, keys: list[bytes] | None = None) -> None:
        self._zcard = zcard
        self._keys = keys or []
        self.zcard_key: str | None = None

    async def zcard(self, key: str) -> int:
        self.zcard_key = key
        return self._zcard

    async def scan_iter(self, match: str | None = None):
        for key in self._keys:
            yield key


class TestQueueDepth:
    """QueueIntrospector.queue_depth"""

    @pytest.mark.asyncio
    async def test_returns_zcard_of_queue_key(self) -> None:
        """Depth is the ZCARD of the arq:queue sorted set."""
        redis = FakeRedis(zcard=7)
        introspector = QueueIntrospector(redis)  # type: ignore[arg-type]
        depth = await introspector.queue_depth()
        assert depth == 7
        assert redis.zcard_key == ARQ_QUEUE_KEY


class TestInProgressIds:
    """QueueIntrospector.in_progress_ids"""

    @pytest.mark.asyncio
    async def test_strips_prefix_from_in_progress_keys(self) -> None:
        """In-progress ids are the keys with the arq:in-progress: prefix removed."""
        redis = FakeRedis(keys=[b"arq:in-progress:abc", b"arq:in-progress:def"])
        introspector = QueueIntrospector(redis)  # type: ignore[arg-type]
        ids = await introspector.in_progress_ids()
        assert sorted(ids) == ["abc", "def"]

    @pytest.mark.asyncio
    async def test_empty_when_no_in_progress_keys(self) -> None:
        """No in-progress keys → empty list."""
        introspector = QueueIntrospector(FakeRedis())  # type: ignore[arg-type]
        assert await introspector.in_progress_ids() == []
