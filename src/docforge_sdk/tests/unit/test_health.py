# ====== Code Summary ======
# Health-resource tests: the probe hits the BARE-root /health route (outside /api/v1, so the authN
# middleware never touches it) and returns a typed HealthStatus. Runs against both clients.

# ====== Third-Party Library Imports ======
import httpx
import respx

# ====== Local Project Imports ======
from docforge_sdk import AsyncClient, Client
from docforge_sdk.models.health import HealthStatus

BASE = "http://test"


@respx.mock
async def test_ping_hits_bare_root_and_returns_status() -> None:
    route = respx.get(f"{BASE}/health").mock(return_value=httpx.Response(200, json={"status": "ok"}))
    async with AsyncClient(BASE, api_token="t") as client:
        result = await client.health.ping()
    assert route.calls.last.request.method == "GET"
    assert route.calls.last.request.url.path == "/health"
    assert isinstance(result, HealthStatus)
    assert result.status == "ok"


@respx.mock
def test_sync_ping_hits_bare_root() -> None:
    route = respx.get(f"{BASE}/health").mock(return_value=httpx.Response(200, json={"status": "ok"}))
    with Client(BASE) as client:
        result = client.health.ping()
    assert route.calls.last.request.url.path == "/health"
    assert isinstance(result, HealthStatus)
