"""Live SSE stream of a job (GET /jobs/{id}/stream). Two layers, no live stack:
1. the poll-backed generator (stream_job_events) driven against a fake jobs facade — asserts the SSE
   frames are well-formed ``data: {...}\\n\\n``, that a newly-landed stage event is pushed, and that
   the loop stops at the terminal status;
2. the route wiring — the endpoint is registered, streams text/event-stream, and 404s an unknown job.
The fake facade yields successive job snapshots + growing event lists across polls; sleep is a no-op
so the test runs with zero real delay."""

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock


def _job(status: str, progress: int, stage: str | None) -> SimpleNamespace:
    """A job row stand-in (status is an enum-like with .value, like the ORM column)."""
    return SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        document_id="22222222-2222-2222-2222-222222222222",
        collection_id="33333333-3333-3333-3333-333333333333",
        status=SimpleNamespace(value=status),
        progress=progress,
        current_stage=stage,
        error=None,
        attempt=1,
        started_at=None,
        finished_at=None,
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        total_prompt_tokens=0,
        total_completion_tokens=0,
        cost_usd=0,
    )


def _event(stage: str, status: str) -> SimpleNamespace:
    """A stage-event row stand-in."""
    return SimpleNamespace(
        stage=stage,
        status=status,
        started_at=None,
        finished_at=None,
        detail="0.1s",
        prompt_tokens=None,
        completion_tokens=None,
        cost_usd=None,
    )


class _FakeJobs:
    """A jobs facade returning successive snapshots + growing event lists, one step per poll."""

    def __init__(self, jobs: list, events: list[list]) -> None:
        self._jobs = jobs
        self._events = events
        self._tick = 0

    async def get(self, _job_id):
        # Clamp to the last snapshot so an extra poll never overruns the timeline.
        job = self._jobs[min(self._tick, len(self._jobs) - 1)]
        return job

    async def list_events(self, _job_id):
        events = self._events[min(self._tick, len(self._events) - 1)]
        self._tick += 1  # advance AFTER a full poll (get then list_events)
        return events


async def _noop_sleep(_seconds: float) -> None:
    """A sleep that yields control without any real delay (keeps the test instant)."""
    await asyncio.sleep(0)


async def _drain(gen) -> list[str]:
    return [frame async for frame in gen]


def _payloads(frames: list[str]) -> list[dict]:
    """Parse each frame's JSON body, asserting it is a well-formed ``data: {...}\\n\\n`` SSE frame."""
    out = []
    for frame in frames:
        assert frame.startswith("data: "), frame
        assert frame.endswith("\n\n"), frame
        out.append(json.loads(frame[len("data: ") :].rstrip("\n")))
    return out


def test_generator_pushes_events_and_stops_at_terminal() -> None:
    """A running→running→done timeline: the new stage events are pushed, a final done status lands,
    and the generator returns (the stream closes) once the job is terminal."""
    from backend.routers.jobs.stream import stream_job_events

    jobs = _FakeJobs(
        jobs=[
            _job("running", 10, "intake"),
            _job("running", 60, "chunk"),
            _job("done", 100, "embed"),
        ],
        events=[
            [_event("intake", "success")],
            [_event("intake", "success"), _event("chunk", "success")],
            [
                _event("intake", "success"),
                _event("chunk", "success"),
                _event("embed", "success"),
            ],
        ],
    )
    frames = asyncio.run(_drain(stream_job_events(jobs, "job", poll_interval=0, sleep=_noop_sleep)))
    payloads = _payloads(frames)

    # 1. Every emitted stage event rode through exactly once (3 distinct events over the 3 polls).
    event_stages = [p["stage"] for p in payloads if p["kind"] == "event"]
    assert event_stages == ["intake", "chunk", "embed"]

    # 2. Status frames only when the snapshot moved (running@10 → running@60 → done@100).
    statuses = [(p["status"], p["progress"]) for p in payloads if p["kind"] == "status"]
    assert statuses == [("running", 10), ("running", 60), ("done", 100)]

    # 3. The stream closed on the terminal status — the last frame is the done status.
    assert payloads[-1]["kind"] == "status" and payloads[-1]["status"] == "done"


def test_generator_closes_on_a_vanished_job() -> None:
    """A job deleted mid-stream (get → None) emits a 'gone' status frame and closes cleanly."""
    from backend.routers.jobs.stream import stream_job_events

    jobs = SimpleNamespace(get=AsyncMock(return_value=None), list_events=AsyncMock(return_value=[]))
    frames = asyncio.run(_drain(stream_job_events(jobs, "job", poll_interval=0, sleep=_noop_sleep)))
    payloads = _payloads(frames)
    assert payloads == [{"kind": "status", "job_id": "job", "status": "gone"}]


def test_stream_route_is_registered(fastapi_app) -> None:
    """The SSE stream is part of the API contract (GET under the job scope)."""
    paths = fastapi_app.openapi()["paths"]
    assert "get" in paths["/api/v1/jobs/{job_id}/stream"]


def test_stream_route_streams_event_stream(client, monkeypatch) -> None:
    """The route resolves + scopes the job, then streams a text/event-stream that ends at terminal."""
    from backend.context import CONTEXT

    monkeypatch.setattr(
        CONTEXT.database.jobs, "get", AsyncMock(return_value=_job("done", 100, "embed"))
    )
    monkeypatch.setattr(
        CONTEXT.database.jobs,
        "list_events",
        AsyncMock(return_value=[_event("embed", "success")]),
    )
    response = client.get("/api/v1/jobs/11111111-1111-1111-1111-111111111111/stream")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    payloads = _payloads([f + "\n\n" for f in response.text.split("\n\n") if f.strip()])
    kinds = {p["kind"] for p in payloads}
    assert kinds == {"event", "status"}
    assert payloads[-1]["status"] == "done"


def test_stream_route_unknown_job_is_404(client, monkeypatch) -> None:
    """An unknown job is a normal 404 resolved BEFORE the stream opens (not buried mid-stream)."""
    from backend.context import CONTEXT

    monkeypatch.setattr(CONTEXT.database.jobs, "get", AsyncMock(return_value=None))
    response = client.get("/api/v1/jobs/11111111-1111-1111-1111-111111111111/stream")
    assert response.status_code == 404, response.text
