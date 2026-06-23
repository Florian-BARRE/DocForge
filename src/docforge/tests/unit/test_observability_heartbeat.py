# ====== Code Summary ======
# Unit tests for the heartbeat writer/reader round-trip and WorkerHeartbeat (de)serialization.

# ====== Standard Library Imports ======
from __future__ import annotations

import json

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from libs.observability.heartbeat import (
    WORKER_KEY_PREFIX,
    HeartbeatReader,
    HeartbeatWriter,
    WorkerHeartbeat,
)


class FakeRedis:
    """In-memory async Redis double covering set/delete/scan_iter/mget."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.last_ex: int | None = None

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value
        self.last_ex = ex

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)

    async def scan_iter(self, match: str | None = None):
        for key in list(self.store):
            yield key

    async def mget(self, keys: list[str]) -> list[str | None]:
        return [self.store.get(k) for k in keys]


def _sample_heartbeat(worker_id: str = "host:1:abcd1234") -> WorkerHeartbeat:
    return WorkerHeartbeat(
        worker_id=worker_id,
        hostname="host",
        pid=1,
        started_at="2026-06-23T00:00:00+00:00",
        last_seen="2026-06-23T00:00:05+00:00",
        status="busy",
        current_job_id="job-1",
        jobs_processed=3,
        cpu_pct=12.5,
        rss_mb=256.0,
        gpu=[{"index": 0, "mem_used_mb": 100, "mem_total_mb": 16000, "util_gpu_pct": 40}],
    )


class TestHeartbeatModel:
    """WorkerHeartbeat (de)serialization."""

    def test_to_dict_from_dict_round_trip(self) -> None:
        """to_dict → from_dict reproduces the heartbeat."""
        hb = _sample_heartbeat()
        restored = WorkerHeartbeat.from_dict(hb.to_dict())
        assert restored == hb

    def test_from_dict_ignores_unknown_keys(self) -> None:
        """Forward-compatible payloads (extra keys) do not break parsing."""
        payload = _sample_heartbeat().to_dict()
        payload["future_field"] = "ignored"
        restored = WorkerHeartbeat.from_dict(payload)
        assert restored.worker_id == "host:1:abcd1234"


class TestWriterReaderRoundTrip:
    """HeartbeatWriter → HeartbeatReader over a shared fake Redis."""

    @pytest.mark.asyncio
    async def test_beat_then_list_workers(self) -> None:
        """A written heartbeat is read back by the reader."""
        redis = FakeRedis()
        writer = HeartbeatWriter(redis, "host:1:abcd1234", ttl_s=15)  # type: ignore[arg-type]
        await writer.beat(_sample_heartbeat())

        # Key is prefixed and TTL applied
        assert f"{WORKER_KEY_PREFIX}host:1:abcd1234" in redis.store
        assert redis.last_ex == 15

        reader = HeartbeatReader(redis)  # type: ignore[arg-type]
        workers = await reader.list_workers()
        assert len(workers) == 1
        assert workers[0].worker_id == "host:1:abcd1234"
        assert workers[0].current_job_id == "job-1"

    @pytest.mark.asyncio
    async def test_remove_deletes_key(self) -> None:
        """remove() drops the heartbeat key (clean shutdown)."""
        redis = FakeRedis()
        writer = HeartbeatWriter(redis, "w1", ttl_s=15)  # type: ignore[arg-type]
        await writer.beat(_sample_heartbeat("w1"))
        await writer.remove()
        reader = HeartbeatReader(redis)  # type: ignore[arg-type]
        assert await reader.list_workers() == []

    @pytest.mark.asyncio
    async def test_reader_skips_malformed_payload(self) -> None:
        """A non-JSON payload is skipped, not fatal."""
        redis = FakeRedis()
        redis.store[f"{WORKER_KEY_PREFIX}broken"] = "not-json"
        reader = HeartbeatReader(redis)  # type: ignore[arg-type]
        assert await reader.list_workers() == []
