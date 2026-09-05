# ====== Code Summary ======
# HttpMetricsMiddleware — a pure ASGI middleware recording per-request Prometheus series: a request
# counter and a latency histogram (labelled by method + route TEMPLATE, plus status on the counter),
# and an in-flight gauge (by method). It is wired OUTER to the auth / rate-limit / idempotency gates so
# 401 / 429 / idempotency replay+reject responses are counted too. Those short-circuit BEFORE routing,
# so the router never stashes ``scope["route"]``; without help such requests would ALL collapse into
# the ``__unmatched__`` bucket alongside genuine 404s. This middleware recovers attribution two ways,
# both label-cardinality-safe and free of any fragile FastAPI-internals walk:
#   • an inner short-circuiting middleware that already knows its route template (the idempotency
#     middleware on a replay/reject) stashes it on the shared scope under ``SCOPE_ROUTE_TEMPLATE`` —
#     the outer metrics middleware then attributes those to the REAL template;
#   • a pre-routing gate rejection (a 401 from auth, a 429 from the rate limiter) has no template to
#     stash, so it is labelled with the distinct ``__gate_rejected__`` sentinel — separated from the
#     genuine-404 ``__unmatched__`` bucket, yet still a single bounded label (never a raw path).
# Using the route TEMPLATE (not the raw path) as a label keeps cardinality bounded.
#
# A long-lived SSE / event-stream response would record its full open duration into the latency
# histogram and skew every quantile, so streaming responses (content-type text/event-stream) are
# EXCLUDED from the latency histogram — they are still counted in the request + in-flight series.

# ====== Standard Library Imports ======
import time

# ====== Third-Party Library Imports ======
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# ====== Local Project Imports ======
from .collectors import DocForgeMetrics

# Shared scope key an inner short-circuiting middleware (e.g. idempotency on a replay/reject) may set
# to hand the already-resolved route TEMPLATE to this outer middleware, so a pre-routing short-circuit
# is still attributed to its real endpoint rather than the __unmatched__ bucket.
SCOPE_ROUTE_TEMPLATE = "docforge.route_template"

# Route label for a request that genuinely matched no route (a 404) — collapsing them under one label
# prevents unbounded label cardinality from junk paths.
_UNMATCHED = "__unmatched__"

# Route label for a request a gate rejected BEFORE routing (401 auth / 429 rate limit): a real endpoint
# was hit but no template is recoverable, so it gets its own bounded bucket, distinct from a 404.
_GATE_REJECTED = "__gate_rejected__"

# The statuses a pre-routing gate emits — used to tell a gate rejection apart from a genuine 404 when
# no route (and no stashed template) is present.
_GATE_STATUSES = frozenset({401, 429})

# The HTTP methods that get their own label; anything else (a forged/junk verb on this unauthenticated,
# on-by-default endpoint) collapses to one bucket so an attacker can't grow the series set unbounded.
_KNOWN_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
_OTHER_METHOD = "OTHER"

# The content-type that marks a Server-Sent-Events stream — excluded from the latency histogram.
_EVENT_STREAM_MEDIA_TYPE = b"text/event-stream"


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

        # 2. Capture the response status AND whether the response is an SSE stream by peeking the
        #    response-start message (its content-type header); the body itself is left untouched.
        status_holder = {"code": 500}
        stream_holder = {"is_stream": False}

        async def _send(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
                stream_holder["is_stream"] = self._is_event_stream(message)
            await send(message)

        # 3. Count the request in-flight and time it end-to-end (finally → also records on failure).
        DocForgeMetrics.HTTP_REQUESTS_IN_PROGRESS.labels(method=method).inc()
        start = time.perf_counter()
        try:
            await self.app(scope, receive, _send)
        finally:
            elapsed = time.perf_counter() - start
            template = self._route_template(scope, status_holder["code"])
            DocForgeMetrics.HTTP_REQUESTS_IN_PROGRESS.labels(method=method).dec()
            # A long-lived SSE stream would skew the latency histogram with its full open duration, so
            # its duration is deliberately NOT observed — the request is still counted below.
            if not stream_holder["is_stream"]:
                DocForgeMetrics.HTTP_REQUEST_DURATION_SECONDS.labels(
                    method=method, path=template
                ).observe(elapsed)
            DocForgeMetrics.HTTP_REQUESTS_TOTAL.labels(
                method=method, path=template, status=str(status_holder["code"])
            ).inc()

    @staticmethod
    def _route_template(scope: Scope, status: int) -> str:
        """
        Return the request's low-cardinality template label, resolving pre-routing short-circuits.

        Args:
            scope (Scope): The ASGI connection scope (the router sets ``route`` once a route matched;
                an inner short-circuiting middleware may set ``SCOPE_ROUTE_TEMPLATE``).
            status (int): The observed response status (distinguishes a gate rejection from a 404).

        Returns:
            str: The route template (e.g. ``/api/v1/jobs/{job_id}``), the stashed template of an
                idempotency replay/reject, ``"__gate_rejected__"`` for a 401/429 gate short-circuit,
                or ``"__unmatched__"`` for a genuine no-match.
        """
        # 1. Happy path: the router stashed the matched APIRoute on the scope during routing.
        route = scope.get("route")
        template = getattr(route, "path", None)
        if template:
            return template
        # 2. An inner middleware that already knew its template (idempotency replay/reject) stashed it.
        stashed = scope.get(SCOPE_ROUTE_TEMPLATE)
        if stashed:
            return stashed
        # 3. A pre-routing gate rejection (401 auth / 429 throttle) has no recoverable template — give
        #    it its own bounded bucket, kept distinct from a genuine 404.
        if status in _GATE_STATUSES:
            return _GATE_REJECTED
        # 4. Genuinely matched nothing (a 404 on a junk path) → the single low-cardinality sentinel.
        return _UNMATCHED

    @staticmethod
    def _is_event_stream(message: Message) -> bool:
        """
        Report whether a response-start message declares a Server-Sent-Events stream.

        Args:
            message (Message): An ``http.response.start`` ASGI message (status + headers).

        Returns:
            bool: True when the ``content-type`` is ``text/event-stream`` (charset suffix ignored).
        """
        # 1. ASGI headers are lower-cased (name, value) byte tuples; match content-type's media type.
        for name, value in message.get("headers", []):
            if name == b"content-type":
                return value.split(b";", 1)[0].strip().lower() == _EVENT_STREAM_MEDIA_TYPE
        return False


__all__ = ["HttpMetricsMiddleware", "SCOPE_ROUTE_TEMPLATE"]
