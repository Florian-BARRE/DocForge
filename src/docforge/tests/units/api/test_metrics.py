# ====== Code Summary ======
# Unit coverage for the Prometheus /metrics endpoint: it returns text/plain, includes the HTTP series
# and the DocForge infra gauges, is auth-exempt (served with auth ON and no bearer), and 404s when
# METRICS_ENABLED is false. Infra sources are stubbed so the scrape is deterministic and serviceless
# (no Redis/Postgres contact), which also asserts the gauges carry the refreshed values.

# ====== Standard Library Imports ======
from types import SimpleNamespace

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


# ── short-circuit route attribution (gate 401/429 + idempotency replay/reject) ─────────────────────


def test_route_template_prefers_matched_route(fastapi_app) -> None:
    """A normally-routed request labels by the route TEMPLATE the router stashed on the scope."""
    from backend.libs.metrics.http_middleware import HttpMetricsMiddleware  # noqa: PLC0415

    scope = {"type": "http", "route": SimpleNamespace(path="/api/v1/collections/{collection_id}")}
    assert (
        HttpMetricsMiddleware._route_template(scope, 200) == "/api/v1/collections/{collection_id}"
    )


def test_route_template_uses_stashed_template_on_short_circuit(fastapi_app) -> None:
    """An idempotency replay/reject short-circuits before routing but stashes its real template.

    This is what stops idempotency replays/rejections collapsing into __unmatched__.
    """
    from backend.libs.metrics.http_middleware import (  # noqa: PLC0415
        SCOPE_ROUTE_TEMPLATE,
        HttpMetricsMiddleware,
    )

    scope = {"type": "http", SCOPE_ROUTE_TEMPLATE: "/api/v1/collections"}
    # Even a 409 reject (no scope['route']) attributes to the real endpoint via the stash.
    assert HttpMetricsMiddleware._route_template(scope, 409) == "/api/v1/collections"


def test_route_template_gate_rejection_gets_distinct_label(fastapi_app) -> None:
    """A 401/429 gate short-circuit (no route, no stash) gets its own bucket, distinct from a 404."""
    from backend.libs.metrics.http_middleware import HttpMetricsMiddleware  # noqa: PLC0415

    assert HttpMetricsMiddleware._route_template({"type": "http"}, 401) == "__gate_rejected__"
    assert HttpMetricsMiddleware._route_template({"type": "http"}, 429) == "__gate_rejected__"


def test_route_template_genuine_404_stays_unmatched(fastapi_app) -> None:
    """A genuine no-match (no route, no stash, a 404 status) collapses to the __unmatched__ sentinel."""
    from backend.libs.metrics.http_middleware import HttpMetricsMiddleware  # noqa: PLC0415

    assert HttpMetricsMiddleware._route_template({"type": "http"}, 404) == "__unmatched__"


# ── SSE streams are counted but excluded from the latency histogram ────────────────────────────────


async def _drive_metrics(*, content_type: bytes, template: str) -> None:
    """Run HttpMetricsMiddleware over a stub downstream sending one response with ``content_type``."""
    from backend.libs.metrics.http_middleware import HttpMetricsMiddleware  # noqa: PLC0415

    async def _downstream(scope, receive, send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", content_type)],
            }
        )
        await send({"type": "http.response.body", "body": b"data: hi\n\n", "more_body": False})

    async def _send(message) -> None:
        return None

    async def _receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/probe",
        "route": SimpleNamespace(path=template),
    }
    await HttpMetricsMiddleware(_downstream)(scope, _receive, _send)


async def test_sse_stream_is_counted_but_not_timed(fastapi_app) -> None:
    """A text/event-stream response is counted in the request counter but NOT observed in latency."""
    from prometheus_client import REGISTRY  # noqa: PLC0415

    template = "__sse_probe__"
    labels = {"method": "GET", "path": template}
    await _drive_metrics(content_type=b"text/event-stream; charset=utf-8", template=template)

    # Counted in the request counter (status 200)...
    assert (
        REGISTRY.get_sample_value("docforge_http_requests_total", {**labels, "status": "200"})
        == 1.0
    )
    # ...but its duration was NOT observed → the histogram label set was never even created.
    assert REGISTRY.get_sample_value("docforge_http_request_duration_seconds_count", labels) is None


async def test_non_stream_response_is_timed(fastapi_app) -> None:
    """The counterpart: a normal JSON response IS observed in the latency histogram."""
    from prometheus_client import REGISTRY  # noqa: PLC0415

    template = "__json_probe__"
    labels = {"method": "GET", "path": template}
    await _drive_metrics(content_type=b"application/json", template=template)

    assert REGISTRY.get_sample_value("docforge_http_request_duration_seconds_count", labels) == 1.0
