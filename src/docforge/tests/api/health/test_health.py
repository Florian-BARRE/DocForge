# ====== Code Summary ======
# Tests for GET /api/v1/health/ping — liveness check.

import httpx
import pytest


class TestPing:
    """GET /api/v1/health/ping"""

    @pytest.mark.asyncio
    async def test_ping_returns_200(self, client: httpx.AsyncClient) -> None:
        """Health endpoint always returns HTTP 200."""
        response = await client.get("/api/v1/health/ping")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_ping_response_body_is_json(self, client: httpx.AsyncClient) -> None:
        """Response body is valid JSON."""
        response = await client.get("/api/v1/health/ping")
        assert response.headers["content-type"].startswith("application/json")

    @pytest.mark.asyncio
    async def test_ping_has_status_field(self, client: httpx.AsyncClient) -> None:
        """Response body must contain a 'status' key."""
        response = await client.get("/api/v1/health/ping")
        assert "status" in response.json()

    @pytest.mark.asyncio
    async def test_ping_status_value_is_ok(self, client: httpx.AsyncClient) -> None:
        """status field must equal 'ok'."""
        response = await client.get("/api/v1/health/ping")
        assert response.json()["status"] == "ok"
