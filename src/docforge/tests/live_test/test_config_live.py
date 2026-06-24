# ====== Code Summary ======
# LIVE coverage of the collection configuration sub-resource: state / schema / history (read) and
# update / rollback (mutations), plus the reindex-flagging contract. Runs on isolated collections
# (no document needed) so it is fast and side-effect free. Verifies the transparency envelope,
# version history growth, credential-free redaction shape, and that an index-invalidating change
# (embedding model) flips needs_reindex.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from tests.live_test.conftest import CORPUS_METADATA_SCHEMA


class TestConfigRead:
    """GET state / schema / history."""

    def test_state_shape(self, make_collection, live_client) -> None:
        """State carries identity, contract, redacted pipeline, schema and embed provider id."""
        col = make_collection(metadata_schema=CORPUS_METADATA_SCHEMA)
        status, state = live_client.get(f"/collections/{col['id']}/config/state")
        assert status == 200, state
        for field in ("id", "name", "pipeline_version", "needs_reindex", "pipeline",
                      "metadata_fields", "embed_provider_id", "supported_formats"):
            assert field in state, f"missing {field} in config state"
        assert state["embed_provider_id"] == "tei"

    def test_schema_includes_system_and_custom_fields(self, make_collection, live_client) -> None:
        """The schema lists caller-provided custom fields plus auto-injected system fields."""
        col = make_collection(metadata_schema=CORPUS_METADATA_SCHEMA)
        status, schema = live_client.get(f"/collections/{col['id']}/config/schema")
        assert status == 200, schema
        names = {f["field_name"] for f in schema["metadata_fields"]}
        assert "dossier" in names and "sujet" in names, "custom fields missing"
        assert any(f["is_system"] for f in schema["metadata_fields"]), "no system fields injected"

    def test_history_records_updates(self, make_collection, live_client) -> None:
        """Each config update appends a version (collection create itself does NOT snapshot)."""
        col = make_collection(unknown_field_policy="reject")
        cid = col["id"]
        # A freshly-created collection may have an empty history; the first update records v1.
        live_client.post(f"/collections/{cid}/config/update",
                         {"patch": {"unknown_field_policy": "ignore"}})
        status, history = live_client.get(f"/collections/{cid}/config/history")
        assert status == 200, history
        assert history["total"] >= 1
        assert len(history["versions"]) == history["total"]

    def test_state_missing_collection_404(self, live_client) -> None:
        """Unknown collection → 404."""
        status, _ = live_client.get(f"/collections/{uuid.uuid4()}/config/state")
        assert status == 404


class TestConfigUpdate:
    """POST update — merge-patch, history growth, transparency envelope, reindex flagging."""

    def test_update_grows_history_and_returns_envelope(self, make_collection, live_client) -> None:
        """A config update snapshots a new version and returns the `applied` transparency envelope."""
        col = make_collection(unknown_field_policy="reject")
        cid = col["id"]
        before = live_client.get(f"/collections/{cid}/config/history")[1]["total"]

        status, state = live_client.post(
            f"/collections/{cid}/config/update",
            {"patch": {"unknown_field_policy": "ignore"}, "note": "relax unknown fields"},
        )
        assert status == 200, state
        assert state["unknown_field_policy"] == "ignore"
        assert state.get("applied") is not None, "missing transparency envelope"

        after = live_client.get(f"/collections/{cid}/config/history")[1]["total"]
        assert after == before + 1, "history did not grow by one"

    def test_embedding_model_change_flags_reindex(self, make_collection, live_client) -> None:
        """Changing the embedding model is index-invalidating → needs_reindex becomes True."""
        col = make_collection()
        cid = col["id"]
        assert live_client.get(f"/collections/{cid}/config/state")[1]["needs_reindex"] is False

        status, state = live_client.post(
            f"/collections/{cid}/config/update",
            {"patch": {"embedding_model": "BAAI/bge-m3-alt"}},
        )
        assert status == 200, state
        assert state["needs_reindex"] is True, "embedding-model change should flag reindex"

    def test_pipeline_redacted_shape(self, make_collection, live_client) -> None:
        """The echoed pipeline is a dict (credentials redacted) and exposes the embed chain."""
        col = make_collection()
        state = live_client.get(f"/collections/{col['id']}/config/state")[1]
        assert isinstance(state["pipeline"], dict)
        assert "embed" in state["pipeline"]


class TestConfigRollback:
    """POST rollback — re-apply a previous snapshot as a new version."""

    def test_rollback_restores_previous_value(self, make_collection, live_client) -> None:
        """Rolling back re-applies an older snapshot's config as a new version."""
        col = make_collection(unknown_field_policy="reject")
        cid = col["id"]

        # 1. Two updates so an OLDER snapshot exists to restore. Collection create does NOT
        #    snapshot, so the "reject" starting state was never recorded — the first recorded
        #    version is the "ignore" update below.
        live_client.post(f"/collections/{cid}/config/update",
                         {"patch": {"unknown_field_policy": "ignore"}})
        live_client.post(f"/collections/{cid}/config/update",
                         {"patch": {"unknown_field_policy": "store"}})

        # 2. Resolve the oldest recorded version (the "ignore" snapshot) and roll back to it
        history = live_client.get(f"/collections/{cid}/config/history")[1]
        oldest = history["versions"][-1]["version"]
        status, state = live_client.post(
            f"/collections/{cid}/config/rollback", {"version": oldest}
        )
        assert status == 200, state

        # 3. The restored value matches that older snapshot; rollback appends a new version
        assert state["unknown_field_policy"] == "ignore"
        after = live_client.get(f"/collections/{cid}/config/history")[1]["total"]
        assert after >= 3, "rollback should append a new history version"

    def test_rollback_unknown_version_404(self, make_collection, live_client) -> None:
        """Rolling back to a non-existent version → 404."""
        col = make_collection()
        status, _ = live_client.post(
            f"/collections/{col['id']}/config/rollback", {"version": 9999}
        )
        assert status == 404

    def test_rollback_version_zero_rejected_422(self, make_collection, live_client) -> None:
        """Version must be >= 1 (ge=1) → 422 for 0."""
        col = make_collection()
        status, _ = live_client.post(
            f"/collections/{col['id']}/config/rollback", {"version": 0}
        )
        assert status == 422
