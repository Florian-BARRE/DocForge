# ====== Code Summary ======
# Unit tests for StaticBearerAuthMiddleware: reject missing/wrong bearer tokens (401), pass valid.

from __future__ import annotations

# ====== Third-Party Library Imports ======
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

# ====== Internal Project Imports ======
from libs.auth import StaticBearerAuthMiddleware

_TOKEN = "secret-token"


def _build_client() -> TestClient:
    """Build a tiny app behind the bearer middleware."""
    async def ok(request) -> JSONResponse:  # noqa: ANN001 - starlette handler signature
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/mcp", ok)])
    app.add_middleware(StaticBearerAuthMiddleware, expected_token=_TOKEN)
    return TestClient(app)


def test_rejects_missing_token() -> None:
    """No Authorization header → 401."""
    assert _build_client().get("/mcp").status_code == 401


def test_rejects_wrong_token() -> None:
    """Wrong bearer token → 401."""
    res = _build_client().get("/mcp", headers={"Authorization": "Bearer nope"})
    assert res.status_code == 401


def test_accepts_correct_token() -> None:
    """Correct bearer token → 200 and the downstream body."""
    res = _build_client().get("/mcp", headers={"Authorization": f"Bearer {_TOKEN}"})
    assert res.status_code == 200
    assert res.json() == {"ok": True}
