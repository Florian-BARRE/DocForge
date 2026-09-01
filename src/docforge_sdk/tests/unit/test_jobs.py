# ====== Code Summary ======
# Jobs-resource tests: the list endpoint threads the collection filter as a QUERY param and returns
# list[JobStatus]; the trace endpoint returns a typed JobTrace. Runs against both clients.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
import httpx
import respx

# ====== Local Project Imports ======
from docforge_sdk import AsyncClient, Client
from docforge_sdk.models.jobs import CancelResult, JobPage, JobStatus, JobTrace

BASE = "http://test"
API = f"{BASE}/api/v1"
CID = "22222222-2222-2222-2222-222222222222"
JID = "55555555-5555-5555-5555-555555555555"

_JOB_SAMPLE: dict[str, Any] = {
    "job_id": JID,
    "document_id": "d1",
    "collection_id": CID,
    "status": "running",
    "progress": 42,
    "current_stage": "parse",
    "error": None,
    "attempt": 1,
    "started_at": None,
    "finished_at": None,
    "updated_at": "2026-08-03T12:00:00Z",
    "stalled": False,
    "total_prompt_tokens": 0,
    "total_completion_tokens": 0,
    "cost_usd": 0.0,
}


@respx.mock
async def test_list_passes_collection_id_query_and_returns_paged_envelope() -> None:
    page = {"total": 1, "limit": 500, "offset": 0, "jobs": [_JOB_SAMPLE]}
    route = respx.get(f"{API}/jobs").mock(return_value=httpx.Response(200, json=page))
    async with AsyncClient(BASE) as client:
        result = await client.jobs.list(CID)
    sent = route.calls.last.request.url
    assert sent.path == "/api/v1/jobs"
    assert sent.params.get("collection_id") == CID
    # The list is now a bounded, paginated envelope: total + limit/offset echo + the page of jobs.
    assert isinstance(result, JobPage)
    assert result.total == 1 and result.limit == 500 and result.offset == 0
    assert len(result.jobs) == 1 and isinstance(result.jobs[0], JobStatus)


@respx.mock
def test_sync_list_threads_limit_and_offset_query_params() -> None:
    page = {"total": 0, "limit": 50, "offset": 100, "jobs": []}
    route = respx.get(f"{API}/jobs").mock(return_value=httpx.Response(200, json=page))
    with Client(BASE) as client:
        result = client.jobs.list(CID, limit=50, offset=100)
    sent = route.calls.last.request.url
    # Paging is threaded as query params; omitted params fall back to the server defaults.
    assert sent.params.get("limit") == "50"
    assert sent.params.get("offset") == "100"
    assert isinstance(result, JobPage) and result.offset == 100


@respx.mock
def test_sync_get_events_returns_trace() -> None:
    route = respx.get(f"{API}/jobs/{JID}/events").mock(
        return_value=httpx.Response(200, json={"job_id": JID, "events": []})
    )
    with Client(BASE) as client:
        result = client.jobs.get_events(JID)
    assert route.calls.last.request.url.path == f"/api/v1/jobs/{JID}/events"
    assert isinstance(result, JobTrace)


@respx.mock
async def test_cancel_defaults_to_non_force_and_returns_typed_result() -> None:
    route = respx.post(f"{API}/jobs/{JID}/cancel").mock(
        return_value=httpx.Response(
            200,
            json={
                "job_id": JID,
                "status": "running",
                "cancel_requested": True,
                "outcome": "cancellation_requested",
                "detail": "Cooperative cancellation requested.",
            },
        )
    )
    async with AsyncClient(BASE) as client:
        result = await client.jobs.cancel(JID)
    sent = route.calls.last.request.url
    assert sent.path == f"/api/v1/jobs/{JID}/cancel"
    assert sent.params.get("force") == "false"
    assert isinstance(result, CancelResult)
    assert result.outcome == "cancellation_requested"


@respx.mock
def test_sync_cancel_passes_force_query_param() -> None:
    route = respx.post(f"{API}/jobs/{JID}/cancel").mock(
        return_value=httpx.Response(
            200,
            json={
                "job_id": JID,
                "status": "cancelled",
                "cancel_requested": False,
                "outcome": "cancelled",
                "detail": "force-terminated while running.",
            },
        )
    )
    with Client(BASE) as client:
        result = client.jobs.cancel(JID, force=True)
    sent = route.calls.last.request.url
    assert sent.params.get("force") == "true"
    assert result.outcome == "cancelled"
