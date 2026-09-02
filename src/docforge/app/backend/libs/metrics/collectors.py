# ====== Code Summary ======
# DocForgeMetrics — the single Prometheus series surface. The HTTP request series are fed passively by
# HttpMetricsMiddleware; the DocForge infra gauges are refreshed at scrape time by MetricsService
# (arq queue depth, job counts by state, live worker count). Every series lives on the default
# prometheus_client registry, so one generate_latest() renders them all. Gauges appear in the
# exposition with a 0 value even before their first refresh, so the schema is stable across scrapes.

# ====== Third-Party Library Imports ======
from prometheus_client import Counter, Gauge, Histogram


class DocForgeMetrics:
    """Static holder of every Prometheus series (each created once, at import time)."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("DocForgeMetrics is a static-only class and cannot be instantiated.")

    # ── HTTP request series (fed by HttpMetricsMiddleware) ────────────────────
    HTTP_REQUESTS_TOTAL = Counter(
        "docforge_http_requests_total",
        "Total HTTP requests by method, route template and status code.",
        ["method", "path", "status"],
    )
    HTTP_REQUEST_DURATION_SECONDS = Histogram(
        "docforge_http_request_duration_seconds",
        "HTTP request latency in seconds by method and route template.",
        ["method", "path"],
    )
    HTTP_REQUESTS_IN_PROGRESS = Gauge(
        "docforge_http_requests_in_progress",
        "In-flight HTTP requests by method.",
        ["method"],
    )

    # ── DocForge infra gauges (refreshed by MetricsService at scrape time) ─────
    ARQ_QUEUE_DEPTH = Gauge(
        "docforge_arq_queue_depth",
        "Ingestion jobs waiting in the arq Redis queue (enqueued, unclaimed).",
    )
    JOBS_PENDING = Gauge(
        "docforge_jobs_pending",
        "Jobs in the PENDING state in the database (admitted, not yet claimed).",
    )
    JOBS_RUNNING = Gauge(
        "docforge_jobs_running",
        "Jobs currently RUNNING (claimed by a worker).",
    )
    JOBS_FAILED = Gauge(
        "docforge_jobs_failed",
        "Jobs currently in the FAILED terminal state.",
    )
    WORKERS_LIVE = Gauge(
        "docforge_workers_live",
        "Workers with a heartbeat fresher than the liveness threshold (alive).",
    )


__all__ = ["DocForgeMetrics"]
