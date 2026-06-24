# ====== Code Summary ======
# LIVE coverage of the observability surface (Briques A/D): the global jobs API (list / get with
# live arq status / cancel) and the monitoring snapshots (queue / workers / overview / resources /
# discovery). Uses the shared ingested corpus so the queue, job history and worker heartbeats are
# populated with real data.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from tests.live_test.conftest import IngestedCorpus


class TestJobs:
    """GET /jobs, GET /jobs/{id}, POST /jobs/{id}/cancel."""

    def test_list_jobs_for_collection(self, ingested_corpus: IngestedCorpus) -> None:
        """Listing jobs filtered to the shared collection returns its ingest jobs."""
        status, body = ingested_corpus.client.get(
            "/jobs", params={"collection_id": ingested_corpus.collection_id, "limit": 100}
        )
        assert status == 200, body
        assert body["total"] >= 1
        assert all(str(j["collection_id"]) == str(ingested_corpus.collection_id) for j in body["jobs"])

    def test_list_jobs_pagination_shape(self, ingested_corpus: IngestedCorpus) -> None:
        """The job list echoes pagination fields."""
        status, body = ingested_corpus.client.get("/jobs", params={"limit": 5, "offset": 0})
        assert status == 200, body
        assert body["limit"] == 5 and body["offset"] == 0
        assert len(body["jobs"]) <= 5

    def test_get_single_job_has_arq_status(self, ingested_corpus: IngestedCorpus) -> None:
        """A single job carries persisted state plus the live arq status field."""
        jobs = ingested_corpus.client.get(
            "/jobs", params={"collection_id": ingested_corpus.collection_id}
        )[1]["jobs"]
        if not jobs:
            pytest.skip("no jobs recorded for the shared collection")
        status, body = ingested_corpus.client.get(f"/jobs/{jobs[0]['id']}")
        assert status == 200, body
        assert body["id"] == jobs[0]["id"]
        assert "arq_status" in body
        assert "progress" in body and "status" in body

    def test_get_unknown_job_404(self, ingested_corpus: IngestedCorpus) -> None:
        """An unknown job id → 404."""
        status, _ = ingested_corpus.client.get(f"/jobs/{uuid.uuid4()}")
        assert status == 404

    def test_cancel_finished_job_returns_200(self, ingested_corpus: IngestedCorpus) -> None:
        """Cancelling an already-finished job is accepted (aborted=False, with a message)."""
        jobs = ingested_corpus.client.get(
            "/jobs", params={"collection_id": ingested_corpus.collection_id}
        )[1]["jobs"]
        if not jobs:
            pytest.skip("no jobs recorded for the shared collection")
        status, body = ingested_corpus.client.post(f"/jobs/{jobs[0]['id']}/cancel")
        assert status == 200, body
        assert "aborted" in body and "message" in body

    def test_cancel_unknown_job_404(self, ingested_corpus: IngestedCorpus) -> None:
        """Cancelling an unknown job id → 404."""
        status, _ = ingested_corpus.client.post(f"/jobs/{uuid.uuid4()}/cancel")
        assert status == 404


class TestMonitoring:
    """GET /monitoring/{queue,workers,overview,resources,discovery}."""

    def test_queue_snapshot(self, ingested_corpus: IngestedCorpus) -> None:
        """Queue snapshot exposes depth, per-status counts and throughput."""
        status, body = ingested_corpus.client.get("/monitoring/queue")
        assert status == 200, body
        for field in ("queue_depth", "counts", "throughput_per_min", "window_minutes"):
            assert field in body

    def test_workers_fleet(self, ingested_corpus: IngestedCorpus) -> None:
        """The worker fleet snapshot lists live workers (the dev worker heartbeats)."""
        status, body = ingested_corpus.client.get("/monitoring/workers")
        assert status == 200, body
        assert "workers" in body and "count" in body
        assert body["count"] == len(body["workers"])

    def test_overview_combines_queue_and_workers(self, ingested_corpus: IngestedCorpus) -> None:
        """The overview bundles queue + workers with a generation timestamp."""
        status, body = ingested_corpus.client.get("/monitoring/overview")
        assert status == 200, body
        assert "queue" in body and "workers" in body and "generated_at" in body

    def test_resources_snapshot(self, ingested_corpus: IngestedCorpus) -> None:
        """The resources snapshot exposes the device gauge + admission limits + live load."""
        status, body = ingested_corpus.client.get("/monitoring/resources")
        assert status == 200, body
        assert "device" in body and "limits" in body
        assert "capabilities" in body["device"]
        assert "queue_depth" in body and "running" in body

    def test_discovery_descriptor(self, ingested_corpus: IngestedCorpus) -> None:
        """The discovery descriptor advertises panels and the SSE stream endpoint."""
        status, body = ingested_corpus.client.get("/monitoring/discovery")
        assert status == 200, body
        assert isinstance(body.get("panels"), list) and body["panels"]
        assert "stream_endpoint" in body
