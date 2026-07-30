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
from docforge_sdk.models.jobs import JobStatus, JobTrace

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
}


@respx.mock
async def test_list_passes_collection_id_query_and_returns_list() -> None:
    route = respx.get(f"{API}/jobs").mock(return_value=httpx.Response(200, json=[_JOB_SAMPLE]))
    async with AsyncClient(BASE) as client:
        result = await client.jobs.list(CID)
    sent = route.calls.last.request.url
    assert sent.path == "/api/v1/jobs"
    assert sent.params.get("collection_id") == CID
    assert len(result) == 1 and isinstance(result[0], JobStatus)


@respx.mock
def test_sync_get_events_returns_trace() -> None:
    route = respx.get(f"{API}/jobs/{JID}/events").mock(
        return_value=httpx.Response(200, json={"job_id": JID, "events": []})
    )
    with Client(BASE) as client:
        result = client.jobs.get_events(JID)
    assert route.calls.last.request.url.path == f"/api/v1/jobs/{JID}/events"
    assert isinstance(result, JobTrace)
