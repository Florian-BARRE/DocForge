# ====== Code Summary ======
# Audit-resource tests: client.audit.list() is a root-only keyset-paginated read on /api/v1/audit;
# supplied filters ride as query params (None → omitted). Runs against both the async and sync client.

# ====== Third-Party Library Imports ======
import httpx
import respx

# ====== Local Project Imports ======
from docforge_sdk import AsyncClient, Client
from docforge_sdk.models.audit import AuditPage

BASE = "http://test"
API = f"{BASE}/api/v1"
_PAGE = {"entries": [], "limit": 50, "next_cursor": None}


@respx.mock
async def test_audit_list_hits_audit_and_threads_filters() -> None:
    route = respx.get(f"{API}/audit").mock(return_value=httpx.Response(200, json=_PAGE))
    async with AsyncClient(BASE, api_token="t") as client:
        result = await client.audit.list(limit=50, target_type="collection")
    request = route.calls.last.request
    assert request.method == "GET"
    assert request.url.path == "/api/v1/audit"
    assert request.url.params["target_type"] == "collection"
    assert request.url.params["limit"] == "50"
    assert isinstance(result, AuditPage)


@respx.mock
async def test_audit_list_omits_unset_filters() -> None:
    route = respx.get(f"{API}/audit").mock(return_value=httpx.Response(200, json=_PAGE))
    async with AsyncClient(BASE, api_token="t") as client:
        await client.audit.list()
    # None filters must not ride the wire — the server applies its own defaults.
    assert "target_type" not in route.calls.last.request.url.params


@respx.mock
def test_sync_audit_list_hits_audit() -> None:
    route = respx.get(f"{API}/audit").mock(return_value=httpx.Response(200, json=_PAGE))
    with Client(BASE) as client:
        result = client.audit.list()
    assert route.calls.last.request.url.path == "/api/v1/audit"
    assert isinstance(result, AuditPage)
