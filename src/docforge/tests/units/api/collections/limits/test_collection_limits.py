# ====== Code Summary ======
# Tests for the per-collection limits sub-resource (Brique D): GET returns the configured cap plus
# live usage (in-flight); PUT replaces the cap. All endpoints live under
# /api/v1/collections/{collection_id}/limits.

# ====== Standard Library Imports ======
import uuid
from unittest.mock import AsyncMock

# ====== Third-Party Library Imports ======
import httpx
import pytest

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from tests.units.api.conftest import make_collection_orm


def _url(collection_id: uuid.UUID) -> str:
    return f"/api/v1/collections/{collection_id}/limits"


def _wire_usage(*, running: int = 0, pending: int = 0) -> None:
    """Point the job_repo mock at fixed live-usage numbers."""
    CONTEXT.job_repo.count_by_status = AsyncMock(return_value={"running": running, "pending": pending})


class TestGetLimits:
    """GET /api/v1/collections/{collection_id}/limits"""

    @pytest.mark.asyncio
    async def test_returns_404_for_unknown_collection(self, client: httpx.AsyncClient) -> None:
        """404 when the collection does not exist."""
        CONTEXT.collection_repo.get_by_id.return_value = None
        _wire_usage()
        response = await client.get(_url(uuid.uuid4()))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_cap_and_live_usage(self, client: httpx.AsyncClient) -> None:
        """200 echoes the configured cap plus computed in-flight."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(
            id=col_id, max_in_flight=5
        )
        _wire_usage(running=2, pending=1)

        body = (await client.get(_url(col_id))).json()
        assert body["collection_id"] == str(col_id)
        assert body["max_in_flight"] == 5
        assert body["in_flight"] == 3

    @pytest.mark.asyncio
    async def test_cap_is_null_when_uncapped(self, client: httpx.AsyncClient) -> None:
        """A collection with no in-flight cap reports null max_in_flight."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.get_by_id.return_value = make_collection_orm(id=col_id)
        _wire_usage()
        body = (await client.get(_url(col_id))).json()
        assert body["max_in_flight"] is None


class TestPutLimits:
    """PUT /api/v1/collections/{collection_id}/limits"""

    @pytest.mark.asyncio
    async def test_returns_404_for_unknown_collection(self, client: httpx.AsyncClient) -> None:
        """404 when update_limits reports no matching collection."""
        CONTEXT.collection_repo.update_limits = AsyncMock(return_value=None)
        _wire_usage()
        response = await client.put(_url(uuid.uuid4()), json={"max_in_flight": 3})
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_replaces_cap_and_echoes_state(self, client: httpx.AsyncClient) -> None:
        """200 returns the refreshed cap and re-computed usage."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.update_limits = AsyncMock(
            return_value=make_collection_orm(id=col_id, max_in_flight=3)
        )
        _wire_usage(running=1, pending=0)

        response = await client.put(_url(col_id), json={"max_in_flight": 3})
        assert response.status_code == 200
        body = response.json()
        assert body["max_in_flight"] == 3
        assert body["in_flight"] == 1

    @pytest.mark.asyncio
    async def test_clears_cap_with_null(self, client: httpx.AsyncClient) -> None:
        """PUT with null clears the cap (unlimited)."""
        col_id = uuid.uuid4()
        CONTEXT.collection_repo.update_limits = AsyncMock(
            return_value=make_collection_orm(id=col_id, max_in_flight=None)
        )
        _wire_usage()
        response = await client.put(_url(col_id), json={"max_in_flight": None})
        assert response.status_code == 200
        body = response.json()
        assert body["max_in_flight"] is None

    @pytest.mark.asyncio
    async def test_rejects_negative_cap(self, client: httpx.AsyncClient) -> None:
        """A negative in-flight cap fails Pydantic validation (422)."""
        response = await client.put(_url(uuid.uuid4()), json={"max_in_flight": -1})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_rejects_zero_cap(self, client: httpx.AsyncClient) -> None:
        """A 0 cap is rejected (422): 'unlimited' is null, not 0 — 0 would freeze the collection."""
        in_flight = await client.put(_url(uuid.uuid4()), json={"max_in_flight": 0})
        assert in_flight.status_code == 422
