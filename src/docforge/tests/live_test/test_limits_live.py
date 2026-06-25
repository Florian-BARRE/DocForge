# ====== Code Summary ======
# LIVE coverage of the per-collection resource-limits sub-resource (Brique D): reading the cap +
# live usage, replacing it via PUT, the "null = unlimited" semantics, and the boundary guard that
# rejects a 0 cap (which would freeze a collection). Runs on isolated collections — no ingestion
# required.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid


class TestLimitsRead:
    """GET /collections/{id}/limits."""

    def test_defaults_are_unlimited(self, make_collection, live_client) -> None:
        """A new collection has no cap and zero live usage."""
        col = make_collection()
        status, body = live_client.get(f"/collections/{col['id']}/limits")
        assert status == 200, body
        assert body["max_in_flight"] is None
        assert body["in_flight"] == 0

    def test_missing_collection_404(self, live_client) -> None:
        """Unknown collection → 404."""
        status, _ = live_client.get(f"/collections/{uuid.uuid4()}/limits")
        assert status == 404


class TestLimitsUpdate:
    """PUT /collections/{id}/limits."""

    def test_set_cap_and_echo(self, make_collection, live_client) -> None:
        """Setting the cap echoes it back."""
        col = make_collection()
        status, body = live_client.put(
            f"/collections/{col['id']}/limits",
            {"max_in_flight": 5},
        )
        assert status == 200, body
        assert body["max_in_flight"] == 5

    def test_clear_cap_with_null(self, make_collection, live_client) -> None:
        """A null cap clears the limit (unlimited)."""
        col = make_collection()
        live_client.put(f"/collections/{col['id']}/limits", {"max_in_flight": 3})
        status, body = live_client.put(
            f"/collections/{col['id']}/limits",
            {"max_in_flight": None},
        )
        assert status == 200, body
        assert body["max_in_flight"] is None

    def test_zero_in_flight_rejected_422(self, make_collection, live_client) -> None:
        """max_in_flight=0 would freeze the collection → 422 (ge=1)."""
        col = make_collection()
        status, _ = live_client.put(f"/collections/{col['id']}/limits", {"max_in_flight": 0})
        assert status == 422

    def test_update_missing_collection_404(self, live_client) -> None:
        """Updating limits on an unknown collection → 404."""
        status, _ = live_client.put(f"/collections/{uuid.uuid4()}/limits", {"max_in_flight": 2})
        assert status == 404
