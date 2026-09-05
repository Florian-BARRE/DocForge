# ====== Code Summary ======
# AuditMiddleware — a pure ASGI middleware that records exactly one append-only `audit_log` row per
# mutating /api/v1 request (POST/PUT/PATCH/DELETE); reads and non-API paths pass straight through with
# zero overhead. It is wired INNER to Auth (so it reads the principal the authN gate injected into
# scope["state"] for the actor) AND INNER to RateLimit (so a throttled 429 never spams the trail, and
# every audited request has actually been routed → the `path` column is a real low-cardinality route
# TEMPLATE, not a raw-id path). It records the final status of every routed outcome — 2xx/4xx/5xx —
# captured by peeking the response-start message like the metrics middleware does.
#
# NON-GOAL — gate short-circuits are deliberately NOT audited: a 401 (failed auth) and a 429 (throttle)
# each short-circuit ABOVE this middleware, so no row is written for them. This is intentional, not a
# gap. Auditing them would require moving the trail OUTSIDE the auth gate, which (a) loses the actor
# attribution the row is built around (no principal exists before the authN gate runs) and (b) lets an
# unauthenticated caller mint unbounded high-cardinality rows via junk paths. Failed-auth / throttle
# telemetry is an authN/rate-limit concern (surfaced via the metrics series), not the mutation trail.
#
# FAIL-SAFE: the row is written in a `finally` AFTER the response has left downstream — so even an
# UNHANDLED exception escaping the handler (a 500-class escape the app's error handling did not convert)
# still records a row (status 500 by default, since no response-start was seen) before that exception
# propagates untouched. Any failure of the write itself is caught, logged and swallowed — audit
# availability can never fail, delay, or change the user's request outcome. Gated by AUDIT_ENABLED
# (default true); off → transparent passthrough.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG
from shared_libs.observability import CorrelationContext

# ====== Local Project Imports ======
from ...context import CONTEXT
from ..ratelimit import RateLimitKeyResolver
from .helpers import AuditHelpers
from .target_parser import AuditTargetParser

logger = loggerplusplus.bind(identifier="Audit")

# Route label for an audited request that never matched a route (a 404 on a mutating verb) — the
# concrete path is used as a last resort so the NOT NULL `path` column is always populated.
_UNMATCHED_FALLBACK = "unmatched"


class AuditMiddleware:
    """Pure ASGI middleware recording one audit row per mutating /api/v1 request (fail-safe)."""

    def __init__(self, app: ASGIApp) -> None:
        """
        Wrap the downstream ASGI application.

        Args:
            app (ASGIApp): The next ASGI application in the stack.
        """
        # 1. Hold the wrapped app; the trail itself lives in Postgres via the audit façade.
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Record one audit row for a mutating API request, else delegate untouched.

        Args:
            scope (Scope): The ASGI connection scope.
            receive (Receive): The ASGI receive channel.
            send (Send): The ASGI send channel.
        """
        # 1. Non-HTTP scopes, a disabled trail, and non-mutating / non-API requests all pass through
        #    with zero added work (the common read path stays untouched).
        if scope["type"] != "http" or not RUNTIME_CONFIG.AUDIT_ENABLED:
            await self.app(scope, receive, send)
            return
        if not AuditHelpers.is_auditable(scope["method"], scope["path"]):
            await self.app(scope, receive, send)
            return

        # 2. Peek the response status by wrapping send (body bytes are untouched).
        status_holder = {"code": 500}

        async def _send(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
            await send(message)

        # 3. Run the request to completion FIRST — the response reaches the client before we record,
        #    so audit work never adds latency to (nor can it fail) the user's request. The record is
        #    written in a `finally` so an UNHANDLED exception escaping the handler (a 500-class escape)
        #    still leaves a row: `status_holder` keeps its default 500 when no response-start was seen.
        #    The original exception then re-raises untouched — auditing never swallows a failure.
        try:
            await self.app(scope, receive, _send)
        finally:
            # 4. Record after the fact, fully fail-safe: any error is logged and swallowed.
            await self._record(scope, status_holder["code"])

    async def _record(self, scope: Scope, status_code: int) -> None:
        """
        Assemble and persist one audit row; swallow (log) any failure.

        Args:
            scope (Scope): The ASGI connection scope (post-routing, so ``route`` is populated).
            status_code (int): The final response status observed on the response-start message.
        """
        try:
            # 1. Actor from the principal the authN middleware injected (root when auth is off).
            principal = scope.get("state", {}).get("principal")
            actor = AuditHelpers.actor(principal)

            # 2. The stored path is the low-cardinality route TEMPLATE. A mutating request that matched
            #    NO route (a 404) collapses to a single sentinel — NOT the raw concrete path — so an
            #    authenticated caller can't spam distinct high-cardinality rows via POST /random paths
            #    (audit retention defaults to keep-forever). Mirrors the metrics middleware's __unmatched__.
            route = scope.get("route")
            path = getattr(route, "path", None) or _UNMATCHED_FALLBACK

            # 3. The target (type + real UUID) is parsed from the concrete path, not the template.
            target_type, target_id = AuditTargetParser.parse(scope["path"])

            # 4. Client ip via the SAME resolver + trust flag the rate limiter keys on (consistency).
            client_ip = RateLimitKeyResolver.client_ip(
                scope, RUNTIME_CONFIG.RATE_LIMIT_TRUST_FORWARDED_FOR
            )

            # 5. Persist the row (correlation id from the shared context bound by RequestId).
            await CONTEXT.database.audit.record(
                method=scope["method"],
                path=path,
                status_code=status_code,
                actor_user_id=actor.user_id,
                actor_key_id=actor.key_id,
                actor_label=actor.label,
                target_type=target_type,
                target_id=target_id,
                correlation_id=CorrelationContext.get(),
                client_ip=client_ip,
            )
        except Exception as error:
            # The audit trail is observability, never a correctness gate — a write failure must not
            # surface to the user (the response is already sent) nor raise out of the ASGI task.
            logger.warning(
                f"Audit record failed (swallowed) for {scope['method']} {scope['path']}: {error}"
            )


__all__ = ["AuditMiddleware"]
