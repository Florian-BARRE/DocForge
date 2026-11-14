# ====== Code Summary ======
# Characterization of the SDK's wire behaviour (safety net of the R-25 transport/resource split):
# for a fixed set of arguments, every public resource method produces one exact HTTP request (method,
# URL with query, headers that matter, body). Three guarantees: the async and the sync client send the
# SAME bytes; that request equals the committed golden; and the call table covers every public method
# and every route of ``tests/route_map.ROUTES``. A diff is a wire-contract decision, never a test to fix.

# ====== Standard Library Imports ======
import re

# ====== Third-Party Library Imports ======
import pytest

# ====== Local Project Imports ======
from tests.characterization.support.golden import assert_matches_golden
from tests.characterization.support.surface import clients_surface, module_surface
from tests.characterization.support.wire_cases import CASES, WireCase
from tests.characterization.support.wire_recorder import BASE, record_async, record_sync
from tests.route_map import ROUTES

_API = f"{BASE}/api/v1"
# The only public method whose route is the bare origin (outside /api/v1), absent from ROUTES.
_BARE_ROUTES = {("GET", "/health")}


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
async def test_async_and_sync_send_byte_identical_requests(case: WireCase) -> None:
    async_record, async_body = await record_async(case)
    sync_record, sync_body = record_sync(case)
    assert async_record == sync_record
    assert async_body == sync_body


async def test_every_recorded_request_matches_the_golden() -> None:
    recorded = {case.case_id: (await record_async(case))[0] for case in CASES}
    assert_matches_golden("wire_requests.json", recorded)


def _public_async_methods() -> set[str]:
    """Every ``<client attribute>.<method>`` an AsyncClient exposes, from the clients' own wiring."""
    resources = clients_surface()["AsyncClient"]["resources"]
    methods: set[str] = set()
    for attribute, qualified in resources.items():
        module_name, class_name = qualified.rsplit(".", 1)
        exported = module_surface(module_name)["exports"][class_name]
        methods |= {f"{attribute}.{name}" for name in exported["methods"]}
    return methods


def test_call_table_covers_every_public_resource_method() -> None:
    covered = {f"{case.resource}.{case.method}" for case in CASES}
    assert covered == _public_async_methods()


def _route_pattern(path: str) -> re.Pattern[str]:
    """Turn ``/api/v1/jobs/{job_id}`` into an anchored regex (``{...}`` matches one segment)."""
    segments = [r"[^/]+" if seg.startswith("{") else re.escape(seg) for seg in path.split("/")]
    return re.compile("^" + "/".join(segments) + "$")


def _route_of(method: str, path: str) -> tuple[str, str] | None:
    """Match a sent request to the most specific route template (most literal characters)."""
    candidates = [
        (route_method, template)
        for route_method, template in ROUTES | _BARE_ROUTES
        if route_method == method and _route_pattern(template).match(path)
    ]
    return max(candidates, key=lambda route: len(re.sub(r"\{[^/]+\}", "", route[1])), default=None)


async def test_recorded_requests_hit_exactly_the_routes_of_the_route_map() -> None:
    hit: set[tuple[str, str]] = set()
    for case in CASES:
        record = (await record_async(case))[0]
        path = record["url"].removeprefix(BASE).split("?")[0]
        route = _route_of(record["method"], path)
        assert route is not None, (
            f"{case.case_id} hit a route absent from route_map: {record['url']}"
        )
        hit.add(route)
    assert hit == ROUTES | _BARE_ROUTES, sorted((ROUTES | _BARE_ROUTES) - hit)
