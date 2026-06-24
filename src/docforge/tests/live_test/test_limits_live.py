# ====== Code Summary ======
# LIVE coverage of the per-collection resource-limits sub-resource (Brique D): reading the caps +
# live usage, replacing them via PUT, the derived remaining-budget arithmetic, the "null =
# unlimited" semantics, and the boundary guards that reject a 0 cap (which would freeze a
# collection). Runs on isolated collections — no ingestion required.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid


class TestLimitsRead:
    """GET /collections/{id}/limits."""

    def test_defaults_are_unlimited(self, make_collection, live_client) -> None:
        """A new collection has no caps and zero live usage."""
        col = make_collection()
        status, body = live_client.get(f"/collections/{col['id']}/limits")
        assert status == 200, body
        assert body["max_in_flight"] is None
        assert body["budget_cap_usd"] is None
        assert body["in_flight"] == 0
        assert body["budget_spent_usd"] == 0
        assert body["budget_remaining_usd"] is None

    def test_missing_collection_404(self, live_client) -> None:
        """Unknown collection → 404."""
        status, _ = live_client.get(f"/collections/{uuid.uuid4()}/limits")
        assert status == 404


class TestLimitsUpdate:
    """PUT /collections/{id}/limits."""

    def test_set_caps_and_derive_remaining(self, make_collection, live_client) -> None:
        """Setting caps echoes them back and derives remaining budget (cap − spent)."""
        col = make_collection()
        status, body = live_client.put(
            f"/collections/{col['id']}/limits",
            {"max_in_flight": 5, "budget_cap_usd": 10.0},
        )
        assert status == 200, body
        assert body["max_in_flight"] == 5
        assert body["budget_cap_usd"] == 10.0
        # No spend yet → remaining equals the cap.
        assert body["budget_remaining_usd"] == 10.0

    def test_clear_caps_with_null(self, make_collection, live_client) -> None:
        """Null caps clear the limits (unlimited) and remaining becomes null."""
        col = make_collection()
        live_client.put(f"/collections/{col['id']}/limits",
                        {"max_in_flight": 3, "budget_cap_usd": 5.0})
        status, body = live_client.put(
            f"/collections/{col['id']}/limits",
            {"max_in_flight": None, "budget_cap_usd": None},
        )
        assert status == 200, body
        assert body["max_in_flight"] is None
        assert body["budget_cap_usd"] is None
        assert body["budget_remaining_usd"] is None

    def test_zero_in_flight_rejected_422(self, make_collection, live_client) -> None:
        """max_in_flight=0 would freeze the collection → 422 (ge=1)."""
        col = make_collection()
        status, _ = live_client.put(f"/collections/{col['id']}/limits", {"max_in_flight": 0})
        assert status == 422

    def test_zero_budget_rejected_422(self, make_collection, live_client) -> None:
        """budget_cap_usd=0 would freeze the collection → 422 (gt=0)."""
        col = make_collection()
        status, _ = live_client.put(f"/collections/{col['id']}/limits", {"budget_cap_usd": 0.0})
        assert status == 422

    def test_update_missing_collection_404(self, live_client) -> None:
        """Updating limits on an unknown collection → 404."""
        status, _ = live_client.put(f"/collections/{uuid.uuid4()}/limits", {"max_in_flight": 2})
        assert status == 404
