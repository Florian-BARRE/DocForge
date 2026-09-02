# ====== Code Summary ======
# HttpMetricsMiddleware — a pure ASGI middleware recording per-request Prometheus series: a request
# counter and a latency histogram (labelled by method + route TEMPLATE, plus status on the counter),
# and an in-flight gauge (by method). It is wired OUTER to the auth / rate-limit gates so 401 / 429
# responses are counted too — those short-circuit before routing, so their route label is
# "__unmatched__". Using the route TEMPLATE (not the raw path) as a label keeps cardinality bounded.

# ====== Standard Library Imports ======
import time

# ====== Third-Party Library Imports ======
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# ====== Local Project Imports ======
from .collectors import DocForgeMetrics

# Route label for a request that never matched a route (a 404, or a request the gates rejected before
# routing) — collapsing them under one label prevents unbounded label cardinality from junk paths.
_UNMATCHED = "__unmatched__"

# The HTTP methods that get their own label; anything else (a forged/junk verb on this unauthenticated,
# on-by-default endpoint) collapses to one bucket so an attacker can't grow the series set unbounded.
_KNOWN_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
_OTHER_METHOD = "OTHER"


class HttpMetricsMiddleware:
    """Pure ASGI middleware feeding the HTTP request Prometheus series for every request."""

    def __init__(self, app: ASGIApp) -> None:
        """
        Wrap the downstream ASGI application.

        Args:
            app (ASGIApp): The next ASGI application in the stack.
        """
        # 1. Hold the wrapped app; the middleware is otherwise stateless (series live on the registry).
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Time and count one HTTP request, then delegate to the wrapped app.

        Args:
            scope (Scope): The ASGI connection scope.
            receive (Receive): The ASGI receive channel.
            send (Send): The ASGI send channel.
        """
        # 1. Only HTTP is measured — pass every other scope type through untouched.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # Normalize to a bounded set — a junk/forged verb must not mint a new label series.
        method = scope["method"] if scope["method"] in _KNOWN_METHODS else _OTHER_METHOD

        # 2. Capture the response status by peeking at the response-start message (body untouched).
        status_holder = {"code": 500}

        async def _send(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
            await send(message)

        # 3. Count the request in-flight and time it end-to-end (finally → also records on failure).
        DocForgeMetrics.HTTP_REQUESTS_IN_PROGRESS.labels(method=method).inc()
        start = time.perf_counter()
        try:
            await self.app(scope, receive, _send)
        finally:
            elapsed = time.perf_counter() - start
            template = self._route_template(scope)
            DocForgeMetrics.HTTP_REQUESTS_IN_PROGRESS.labels(method=method).dec()
            DocForgeMetrics.HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method, path=template
            ).observe(elapsed)
            DocForgeMetrics.HTTP_REQUESTS_TOTAL.labels(
                method=method, path=template, status=str(status_holder["code"])
            ).inc()

    @staticmethod
    def _route_template(scope: Scope) -> str:
        """
        Return the matched route's low-cardinality template, or a sentinel when none matched.

        Args:
            scope (Scope): The ASGI connection scope (FastAPI sets ``route`` once a route matched).

        Returns:
            str: The route template (e.g. ``/api/v1/jobs/{job_id}``) or ``"__unmatched__"``.
        """
        # 1. FastAPI stashes the matched APIRoute on the scope during routing — use its path template.
        route = scope.get("route")
        template = getattr(route, "path", None)
        return template or _UNMATCHED


__all__ = ["HttpMetricsMiddleware"]
