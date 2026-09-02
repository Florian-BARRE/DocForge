# ====== Code Summary ======
# Unit coverage for the Prometheus /metrics endpoint: it returns text/plain, includes the HTTP series
# and the DocForge infra gauges, is auth-exempt (served with auth ON and no bearer), and 404s when
# METRICS_ENABLED is false. Infra sources are stubbed so the scrape is deterministic and serviceless
# (no Redis/Postgres contact), which also asserts the gauges carry the refreshed values.

# ====== Third-Party Library Imports ======
import pytest


@pytest.fixture
def stub_infra(monkeypatch):
    """Stub the metrics service's infra sources so a scrape is deterministic and serviceless."""
    from backend import CONTEXT  # noqa: PLC0415
    from shared_libs.services.db.postgresql.tables import JobStatus  # noqa: PLC0415

    async def _queue_depth() -> int:
        return 3

    async def _status_counts() -> dict:
        return {JobStatus.PENDING: 5, JobStatus.RUNNING: 2, JobStatus.FAILED: 1}

    async def _list_heartbeats() -> list:
        return []

    monkeypatch.setattr(CONTEXT.queue, "queue_depth", _queue_depth)
    monkeypatch.setattr(CONTEXT.database.jobs, "status_counts", _status_counts)
    monkeypatch.setattr(CONTEXT.database.jobs, "list_heartbeats", _list_heartbeats)


def test_metrics_returns_prometheus_text(client, monkeypatch, stub_infra) -> None:
    """GET /metrics returns text/plain with the HTTP series and infra gauges refreshed."""
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "METRICS_ENABLED", True)

    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")

    body = response.text
    # HTTP request series (fed by the metrics middleware) are present.
    assert "docforge_http_requests_total" in body
    assert "docforge_http_request_duration_seconds" in body
    # Infra gauges are present AND carry the stubbed values.
    assert "docforge_arq_queue_depth 3.0" in body
    assert "docforge_jobs_pending 5.0" in body
    assert "docforge_jobs_running 2.0" in body
    assert "docforge_jobs_failed 1.0" in body
    assert "docforge_workers_live 0.0" in body


def test_metrics_exempt_from_auth(client, monkeypatch, stub_infra) -> None:
    """With auth ON and no bearer, /metrics is still served (it lives outside /api/v1)."""
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "METRICS_ENABLED", True)
    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)

    response = client.get("/metrics")  # no Authorization header
    assert response.status_code == 200
    assert "docforge_arq_queue_depth" in response.text


def test_metrics_disabled_returns_404(client, monkeypatch) -> None:
    """With METRICS_ENABLED false the endpoint is hidden (404), without unwiring it."""
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "METRICS_ENABLED", False)
    response = client.get("/metrics")
    assert response.status_code == 404


def test_metrics_method_label_is_bounded(client, monkeypatch, stub_infra) -> None:
    """A forged/junk HTTP verb collapses to method="OTHER" — no unbounded label series minting."""
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "METRICS_ENABLED", True)

    # An arbitrary non-standard verb must not become its own metric label.
    client.request("FROBNICATE", "/health")
    body = client.get("/metrics").text
    assert "FROBNICATE" not in body
    assert 'method="OTHER"' in body


def test_metrics_excluded_from_openapi(client) -> None:
    """/metrics is registered with include_in_schema=False, so it never enters the OpenAPI doc."""
    schema = client.get("/openapi.json").json()
    assert "/metrics" not in schema.get("paths", {})
