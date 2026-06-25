# ====== Code Summary ======
# Unit tests for ResourceAdmitter (Brique D): the pure evaluate() decision matrix (capacity 429,
# sentinels, precedence, disabled) and the fail-soft admit() wrapper (introspection errors must
# ADMIT, never block ingestion). All inputs are hand-built — no DB / Redis needed.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from backend.libs.admission import (
    AdmissionSnapshot,
    ResourceAdmitter,
    ResourceLimits,
)


def _admitter(*, enabled: bool = True) -> ResourceAdmitter:
    """Build an admitter; globals are irrelevant to evaluate() (it reads the ResourceLimits)."""
    return ResourceAdmitter(enabled=enabled, max_queue_depth=0, max_in_flight_global=0)


def _snapshot(
    *, queue_depth: int = 0, running_global: int = 0, inflight_collection: int = 0
) -> AdmissionSnapshot:
    """Build a load snapshot with all-quiet defaults; override one signal per test."""
    return AdmissionSnapshot(
        queue_depth=queue_depth,
        running_global=running_global,
        inflight_collection=inflight_collection,
    )


class _FakeCollection:
    """Minimal collection carrying only the per-collection cap the admitter reads."""

    def __init__(self, *, max_in_flight: int | None = None) -> None:
        self.id = uuid.uuid4()
        self.max_in_flight = max_in_flight


class _FakeQueue:
    """QueueIntrospector stand-in returning a fixed backlog depth (or raising)."""

    def __init__(self, depth: int = 0, *, boom: bool = False) -> None:
        self._depth = depth
        self._boom = boom

    async def queue_depth(self) -> int:
        if self._boom:
            raise RuntimeError("redis down")
        return self._depth


class _FakeJobRepo:
    """JobRepository stand-in for global/per-collection counts."""

    def __init__(self, *, running_global: int = 0, coll_running: int = 0, coll_pending: int = 0) -> None:
        self._running_global = running_global
        self._coll_running = coll_running
        self._coll_pending = coll_pending

    async def count_by_status(self, session, *, collection_id=None) -> dict[str, int]:
        if collection_id is None:
            return {"running": self._running_global}
        return {"running": self._coll_running, "pending": self._coll_pending}


class TestEvaluateMatrix:
    """evaluate() is pure: maps (snapshot, limits) to an AdmissionDecision."""

    def test_admits_when_all_under_limits(self) -> None:
        """Everything quiet and well under caps → admit."""
        decision = _admitter().evaluate(
            _snapshot(queue_depth=1, running_global=1, inflight_collection=1),
            ResourceLimits(max_queue_depth=10, max_in_flight_global=10, max_in_flight_collection=10),
        )
        assert decision.admitted is True

    def test_rejects_429_on_global_in_flight(self) -> None:
        """Global running count at the cap → 429 capacity rejection."""
        decision = _admitter().evaluate(
            _snapshot(running_global=8),
            ResourceLimits(max_queue_depth=0, max_in_flight_global=8),
        )
        assert decision.admitted is False
        assert decision.status_code == 429

    def test_rejects_429_on_queue_backlog(self) -> None:
        """Backlog depth at the cap → 429 capacity rejection."""
        decision = _admitter().evaluate(
            _snapshot(queue_depth=100),
            ResourceLimits(max_queue_depth=100, max_in_flight_global=0),
        )
        assert decision.admitted is False
        assert decision.status_code == 429

    def test_rejects_429_on_per_collection_in_flight(self) -> None:
        """Per-collection in-flight at the cap → 429 capacity rejection."""
        decision = _admitter().evaluate(
            _snapshot(inflight_collection=5),
            ResourceLimits(max_queue_depth=0, max_in_flight_global=0, max_in_flight_collection=5),
        )
        assert decision.admitted is False
        assert decision.status_code == 429

    def test_zero_is_unlimited_sentinel_for_globals(self) -> None:
        """max_queue_depth=0 and max_in_flight_global=0 never throttle, even under heavy load."""
        decision = _admitter().evaluate(
            _snapshot(queue_depth=10_000, running_global=10_000),
            ResourceLimits(max_queue_depth=0, max_in_flight_global=0),
        )
        assert decision.admitted is True

    def test_none_per_collection_cap_never_throttles(self) -> None:
        """max_in_flight_collection=None means no per-collection cap."""
        decision = _admitter().evaluate(
            _snapshot(inflight_collection=10_000),
            ResourceLimits(max_queue_depth=0, max_in_flight_global=0, max_in_flight_collection=None),
        )
        assert decision.admitted is True

    def test_disabled_admitter_always_admits(self) -> None:
        """A disabled admitter admits even when every cap is breached."""
        decision = _admitter(enabled=False).evaluate(
            _snapshot(queue_depth=10_000, running_global=10_000),
            ResourceLimits(max_queue_depth=1, max_in_flight_global=1),
        )
        assert decision.admitted is True


class TestAdmitWrapper:
    """admit() composes gather + evaluate, reads per-collection caps, and is fail-soft."""

    @pytest.mark.asyncio
    async def test_admit_reads_per_collection_caps_and_rejects(self) -> None:
        """A collection cap of 2 with 2 jobs in flight → 429 from the gathered snapshot."""
        admitter = _admitter()
        collection = _FakeCollection(max_in_flight=2)
        decision = await admitter.admit(
            session=None,
            collection=collection,
            queue_introspector=_FakeQueue(depth=0),
            job_repo=_FakeJobRepo(coll_running=2, coll_pending=0),
        )
        assert decision.admitted is False
        assert decision.status_code == 429

    @pytest.mark.asyncio
    async def test_admit_passes_when_under_caps(self) -> None:
        """Quiet system, generous caps → admit."""
        admitter = _admitter()
        collection = _FakeCollection(max_in_flight=10)
        decision = await admitter.admit(
            session=None,
            collection=collection,
            queue_introspector=_FakeQueue(depth=1),
            job_repo=_FakeJobRepo(running_global=1, coll_running=1),
        )
        assert decision.admitted is True

    @pytest.mark.asyncio
    async def test_admit_is_fail_soft_on_introspection_error(self) -> None:
        """A Redis/Postgres failure during gather must ADMIT (never block ingestion)."""
        admitter = _admitter()
        decision = await admitter.admit(
            session=None,
            collection=_FakeCollection(max_in_flight=1),
            queue_introspector=_FakeQueue(boom=True),
            job_repo=_FakeJobRepo(),
        )
        assert decision.admitted is True

    @pytest.mark.asyncio
    async def test_admit_disabled_short_circuits_without_io(self) -> None:
        """A disabled admitter never touches the introspectors (would raise if it did)."""
        admitter = _admitter(enabled=False)
        decision = await admitter.admit(
            session=None,
            collection=_FakeCollection(),
            queue_introspector=_FakeQueue(boom=True),
            job_repo=_FakeJobRepo(),
        )
        assert decision.admitted is True
