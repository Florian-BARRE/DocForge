# ====== Code Summary ======
# Route-path coverage guard — the counterpart to test_models_offline_parity's schema completeness
# check. Every (method, path) the committed OpenAPI snapshot exposes must be either a wired SDK
# resource method (tests.route_map.ROUTES) or an explicit, reasoned exemption
# (tests.route_map.EXEMPT_ROUTES). Together these two guards close the "a new backend endpoint merges
# with a green gate and no SDK method" hole: the schema/route sets a new endpoint introduces used to be
# invisible to every parity guard because all three only ever iterated tests/parity_map.MODELS.

# ====== Standard Library Imports ======
import json
from pathlib import Path
from typing import Any

# ====== Third-Party Library Imports ======
import pytest

# ====== Local Project Imports ======
from tests.route_map import EXEMPT_ROUTES, ROUTES

_SNAPSHOT = Path(__file__).resolve().parents[1] / "openapi_snapshot.json"
_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _snapshot_routes() -> set[tuple[str, str]]:
    """
    Load every (METHOD, path) the committed OpenAPI snapshot documents, or skip when it is missing.

    Returns:
        set[tuple[str, str]]: One ``(HTTP method, path)`` pair per operation in ``paths``.
    """
    if not _SNAPSHOT.exists():
        pytest.skip("OpenAPI snapshot not available — skipping route coverage check.")
    spec: dict[str, Any] = json.loads(_SNAPSHOT.read_text())
    return {
        (method.upper(), path)
        for path, operations in spec["paths"].items()
        for method in operations
        if method in _HTTP_METHODS
    }


def test_every_snapshot_route_is_tracked() -> None:
    """Every backend route is either wired (ROUTES) or exempted (EXEMPT_ROUTES) with a reason."""
    tracked = ROUTES | set(EXEMPT_ROUTES)
    missing = _snapshot_routes() - tracked
    assert not missing, (
        "untracked OpenAPI routes — add the SDK resource method to ROUTES, or an exemption with a "
        f"reason to EXEMPT_ROUTES, in tests/route_map.py: {sorted(missing)}"
    )


def test_no_stale_tracked_routes() -> None:
    """Every tracked/exempted route must still exist in the backend — catches a silent removal."""
    stale = (ROUTES | set(EXEMPT_ROUTES)) - _snapshot_routes()
    assert not stale, (
        f"routes tracked in tests/route_map.py no longer exist in the backend: {sorted(stale)}"
    )


@pytest.mark.parametrize("route", list(EXEMPT_ROUTES))
def test_exempt_routes_have_a_reason(route: tuple[str, str]) -> None:
    # Documents WHY a route is exempt from SDK coverage so the exemption is explicit, not silent.
    assert EXEMPT_ROUTES[route]
