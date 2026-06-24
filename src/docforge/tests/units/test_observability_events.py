# ====== Code Summary ======
# Unit tests for EventPublisher — verifies events land on the shared channel with a typed body.

# ====== Standard Library Imports ======
from __future__ import annotations

import json

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from libs.observability.events import EVENTS_CHANNEL, EventPublisher, EventType


class FakeRedis:
    """Records publish() calls."""

    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, message: str) -> None:
        self.published.append((channel, message))


class TestEventPublisher:
    """EventPublisher publishing helpers."""

    @pytest.mark.asyncio
    async def test_publish_uses_shared_channel_with_typed_body(self) -> None:
        """publish() writes to the monitoring channel with the type merged into the payload."""
        redis = FakeRedis()
        await EventPublisher(redis).publish(EventType.JOB_UPDATED, {"id": "j1"})  # type: ignore[arg-type]

        assert len(redis.published) == 1
        channel, raw = redis.published[0]
        assert channel == EVENTS_CHANNEL
        body = json.loads(raw)
        assert body["type"] == "job.updated"
        assert body["id"] == "j1"

    @pytest.mark.asyncio
    async def test_stage_progress_helper_shape(self) -> None:
        """stage_progress() carries job id, stage, percent and null scope keys by default."""
        redis = FakeRedis()
        await EventPublisher(redis).stage_progress("j1", "s4", 55)  # type: ignore[arg-type]
        body = json.loads(redis.published[0][1])
        assert body == {
            "type": "stage.progress", "job_id": "j1", "stage": "s4", "progress": 55,
            "collection_id": None, "document_id": None,
        }

    @pytest.mark.asyncio
    async def test_stage_progress_carries_scope_for_sse_filtering(self) -> None:
        """stage_progress() forwards collection_id/document_id so the SSE layer can scope it."""
        redis = FakeRedis()
        await EventPublisher(redis).stage_progress(  # type: ignore[arg-type]
            "j1", "s4", 55, collection_id="c1", document_id="d1",
        )
        body = json.loads(redis.published[0][1])
        assert body["collection_id"] == "c1"
        assert body["document_id"] == "d1"

    @pytest.mark.asyncio
    async def test_publish_swallows_redis_failure(self) -> None:
        """A publish failure is logged and swallowed — telemetry never breaks the pipeline."""
        class BrokenRedis:
            async def publish(self, channel: str, message: str) -> None:
                raise RuntimeError("redis down")

        # Should not raise
        await EventPublisher(BrokenRedis()).job_updated({"id": "j1"})  # type: ignore[arg-type]
