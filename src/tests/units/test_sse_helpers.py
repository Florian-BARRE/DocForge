# ====== Code Summary ======
# Unit tests for SseHelpers — the collection-scoping predicate (which events reach a collection's
# document stream) and the stream() builder (subscribes to the broadcaster, returns an SSE response).

# ====== Standard Library Imports ======
from __future__ import annotations

import asyncio

# ====== Third-Party Library Imports ======
import pytest
from sse_starlette.sse import EventSourceResponse

# ====== Internal Project Imports ======
from backend.libs.utils.sse import SseHelpers


class _FakeBroadcaster:
    """Minimal stand-in exposing subscribe()/unsubscribe() for stream()."""

    def __init__(self) -> None:
        self.subscribed = 0
        self.unsubscribed = 0

    def subscribe(self) -> asyncio.Queue:
        self.subscribed += 1
        return asyncio.Queue(maxsize=10)

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self.unsubscribed += 1


class TestCollectionPredicate:
    """collection_predicate keeps only events targeting the given collection."""

    def test_job_updated_matches_nested_collection_id(self) -> None:
        """job.updated nests collection_id under 'job' — matching id passes."""
        keep = SseHelpers.collection_predicate("c1")
        assert keep({"type": "job.updated", "job": {"collection_id": "c1", "id": "j1"}}) is True

    def test_job_updated_rejects_other_collection(self) -> None:
        """A job for a different collection is filtered out."""
        keep = SseHelpers.collection_predicate("c1")
        assert keep({"type": "job.updated", "job": {"collection_id": "c2"}}) is False

    def test_job_updated_missing_job_is_safe(self) -> None:
        """A malformed job.updated without a 'job' body is rejected, not raised."""
        keep = SseHelpers.collection_predicate("c1")
        assert keep({"type": "job.updated"}) is False

    def test_stage_progress_matches_top_level_collection_id(self) -> None:
        """stage.progress carries collection_id at the top level (brique C enrichment)."""
        keep = SseHelpers.collection_predicate("c1")
        assert keep({"type": "stage.progress", "collection_id": "c1", "progress": 50}) is True

    def test_stage_progress_rejects_other_collection(self) -> None:
        """stage.progress for another collection is filtered out."""
        keep = SseHelpers.collection_predicate("c1")
        assert keep({"type": "stage.progress", "collection_id": "c2"}) is False

    def test_worker_heartbeat_excluded(self) -> None:
        """Non document-scoped events (e.g. worker.heartbeat) never reach a document stream."""
        keep = SseHelpers.collection_predicate("c1")
        assert keep({"type": "worker.heartbeat", "worker": {"id": "w1"}}) is False


class TestStream:
    """stream() wires the broadcaster into an SSE response."""

    def test_cannot_instantiate(self) -> None:
        """SseHelpers is a static-only class."""
        with pytest.raises(TypeError):
            SseHelpers()

    def test_stream_subscribes_and_returns_sse_response(self) -> None:
        """stream() registers one subscriber queue and returns an EventSourceResponse."""
        broadcaster = _FakeBroadcaster()
        response = SseHelpers.stream(broadcaster, keepalive=15)  # type: ignore[arg-type]
        assert isinstance(response, EventSourceResponse)
        assert broadcaster.subscribed == 1
