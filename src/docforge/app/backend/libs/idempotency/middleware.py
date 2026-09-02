# ====== Code Summary ======
# IdempotencyMiddleware — a pure ASGI middleware giving DocForge Stripe-style idempotency on the small
# set of eligible mutating JSON endpoints. When IDEMPOTENCY_ENABLED and a mutating request to an
# eligible route carries an ``Idempotency-Key`` header, it: (1) fingerprints the body, (2) INSERTs an
# in-progress guard row (the UNIQUE constraint is the concurrency guard), (3a) if it WON the insert,
# runs the handler once, buffers the response, and — only for a definitive (< 500) outcome — caches it
# so retries replay it (a 5xx/exception drops the row so a retry re-runs), (3b) if the row already
# existed, replays the cached response (same key+body → 200 + ``Idempotency-Replayed: true``), or
# rejects a body mismatch (422) or an in-flight duplicate (409). Everything else is a transparent
# passthrough. It is wired INNER to Auth+RateLimit (needs the principal; replays still cost budget) and
# OUTER to Audit (a replay does no new work → it is NOT re-audited; the operation was audited on its
# one real execution).

# ====== Standard Library Imports ======
from __future__ import annotations

from datetime import UTC, datetime, timedelta

# ====== Third-Party Library Imports ======
from fastapi.responses import JSONResponse, Response
from loggerplusplus import loggerplusplus
from starlette.types import ASGIApp, Receive, Scope, Send

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG
from shared_libs.services.db.facades import IdempotencyRecord
from shared_libs.services.db.postgresql.tables import IdempotencyState

# ====== Local Project Imports ======
from ...context import CONTEXT
from .actor import IdempotencyActorScope
from .eligibility import IdempotencyEligibility
from .request_buffer import IdempotencyRequestBuffer
from .response_buffer import IdempotencyResponseBuffer

logger = loggerplusplus.bind(identifier="Idempotency")

# Only these verbs mutate state; a read never carries an idempotency guard.
_MUTATING_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# The client-supplied header carrying the key, and the marker stamped on a replayed response.
_KEY_HEADER = b"idempotency-key"
_REPLAYED_HEADER = "Idempotency-Replayed"

# Responses at or above this status are transient (server-side) → never cached (a retry must re-run).
_SERVER_ERROR_FLOOR = 500


class IdempotencyMiddleware:
    """Pure ASGI middleware providing Idempotency-Key dedup on eligible mutating endpoints."""

    def __init__(self, app: ASGIApp) -> None:
        """
        Wrap the downstream ASGI application.

        Args:
            app (ASGIApp): The next ASGI application in the stack.
        """
        # 1. Hold the wrapped app; the store lives in Postgres via the idempotency façade.
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Apply idempotency to an eligible keyed request, else delegate untouched.

        Args:
            scope (Scope): The ASGI connection scope.
            receive (Receive): The ASGI receive channel.
            send (Send): The ASGI send channel.
        """
        # 1. Cheap passthrough gates: non-HTTP, feature off, or a non-mutating verb.
        if scope["type"] != "http" or not RUNTIME_CONFIG.IDEMPOTENCY_ENABLED:
            await self.app(scope, receive, send)
            return
        if scope["method"] not in _MUTATING_METHODS:
            await self.app(scope, receive, send)
            return

        # 2. No key header → transparent passthrough (idempotency is strictly opt-in per request).
        key = self._header(scope, _KEY_HEADER)
        if key is None:
            await self.app(scope, receive, send)
            return

        # 3. Only the explicit allow-list is guarded; anything else passes through with its raw body.
        template = IdempotencyEligibility.match(scope["method"], scope["path"])
        if template is None:
            await self.app(scope, receive, send)
            return

        # 4. Buffer the body to fingerprint it (and to re-feed the handler). An over-cap body skips
        #    idempotency entirely — the already-read + remaining bytes stream through, never buffered.
        buffer = await IdempotencyRequestBuffer.read(
            receive, RUNTIME_CONFIG.IDEMPOTENCY_MAX_BODY_BYTES
        )
        replay_receive = buffer.replay_receive(receive)
        if buffer.over_cap:
            logger.warning(
                f"Request body over the idempotency cap "
                f"({RUNTIME_CONFIG.IDEMPOTENCY_MAX_BODY_BYTES}B) on {scope['method']} {template}; "
                f"skipping idempotency (passthrough)."
            )
            await self.app(scope, replay_receive, send)
            return

        # 5. Guard-insert then dispatch on the outcome (won the race vs replay/conflict).
        await self._guard(scope, replay_receive, send, template, key, buffer.fingerprint)

    async def _guard(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        template: str,
        key: str,
        fingerprint: str,
    ) -> None:
        """
        Run the guard INSERT and either execute the handler once or replay/reject the duplicate.

        Args:
            scope (Scope): The ASGI connection scope.
            receive (Receive): The replay receive channel (re-feeds the buffered body).
            send (Send): The ASGI send channel.
            template (str): The matched route TEMPLATE (the store's low-cardinality ``path``).
            key (str): The client-supplied idempotency key.
            fingerprint (str): sha256 hex of the request body.
        """
        # 1. Resolve the never-null actor scope + the TTL horizon for a fresh record.
        actor_scope = IdempotencyActorScope.resolve(scope.get("state", {}).get("principal"))
        expires_at = datetime.now(UTC) + timedelta(hours=RUNTIME_CONFIG.IDEMPOTENCY_TTL_HOURS)

        # 2. Attempt the guard INSERT — created means THIS request won and must run the handler.
        begin = await CONTEXT.database.idempotency.begin(
            actor_scope=actor_scope,
            method=scope["method"],
            path=template,
            idempotency_key=key,
            request_fingerprint=fingerprint,
            expires_at=expires_at,
        )
        if begin.created:
            await self._execute(scope, receive, send, actor_scope, template, key)
            return

        # 3. The row already existed — replay the cached response or reject the duplicate.
        await self._replay_or_reject(scope, receive, send, begin.record, fingerprint)

    async def _execute(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        actor_scope: str,
        template: str,
        key: str,
    ) -> None:
        """
        Run the handler once, buffer its response, and cache a definitive outcome (drop a 5xx).

        Args:
            scope (Scope): The ASGI connection scope.
            receive (Receive): The replay receive channel (re-feeds the buffered body).
            send (Send): The ASGI send channel.
            actor_scope (str): The resolved actor scope of the in-progress record.
            template (str): The matched route TEMPLATE.
            key (str): The client-supplied idempotency key.
        """
        # 1. Run the handler with its response buffered (not yet sent to the client).
        buffer = IdempotencyResponseBuffer()
        try:
            await self.app(scope, receive, buffer.send)
        except Exception:
            # 2. The handler raised → NOT replayable: drop the guard row so a retry re-runs, then let
            #    the exception propagate to the outer error handling (nothing was sent to the client).
            await self._safe_drop(actor_scope, scope["method"], template, key)
            raise

        # 3. Cache only a definitive (< 500) outcome; a 5xx is transient → drop the row so a retry
        #    can re-run. Either way the buffered response is flushed to the client afterwards.
        status = buffer.status
        if status is not None and status < _SERVER_ERROR_FLOOR:
            await self._safe_complete(actor_scope, scope["method"], template, key, buffer)
        else:
            await self._safe_drop(actor_scope, scope["method"], template, key)

        # 4. Flush the handler's exact response to the client (deferred until the decision was made).
        await buffer.flush(send)

    async def _replay_or_reject(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        record: IdempotencyRecord | None,
        fingerprint: str,
    ) -> None:
        """
        Given an existing record, replay its cached response or reject the duplicate (409 / 422).

        Args:
            scope (Scope): The ASGI connection scope.
            receive (Receive): The replay receive channel.
            send (Send): The ASGI send channel.
            record (IdempotencyRecord | None): The existing record (None if it vanished mid-race →
                treated as still in progress → 409).
            fingerprint (str): sha256 hex of THIS request's body (compared to the stored one).
        """
        # 1. A vanished record (deleted between the failed insert and the read) or a still-running one
        #    → the operation is in flight; the client should retry later.
        if record is None or record.state != IdempotencyState.completed:
            await self._reject(
                scope, receive, send, 409, "A request with this key is still in progress."
            )
            return

        # 2. Completed but with a DIFFERENT body → the key was reused for another request (client bug).
        if record.request_fingerprint != fingerprint:
            await self._reject(
                scope, receive, send, 422, "Idempotency-Key reused with a different request body."
            )
            return

        # 3. Completed with the SAME body → replay the cached response verbatim + the replay marker.
        response = Response(
            content=record.response_body or b"",
            status_code=record.response_status or 200,
            media_type=record.response_media_type,
            headers={_REPLAYED_HEADER: "true"},
        )
        await response(scope, receive, send)

    async def _reject(
        self, scope: Scope, receive: Receive, send: Send, status_code: int, detail: str
    ) -> None:
        """
        Send a JSON error for a duplicate that cannot be replayed (409 in-progress / 422 body reuse).

        Args:
            scope (Scope): The ASGI connection scope.
            receive (Receive): The replay receive channel.
            send (Send): The ASGI send channel.
            status_code (int): The rejection status (409 or 422).
            detail (str): The human-readable reason (mirrors the app's ``detail`` error shape).
        """
        # 1. A JSON body matching the shape the auth/rate-limit gates return.
        response = JSONResponse({"detail": detail}, status_code=status_code)
        await response(scope, receive, send)

    async def _safe_complete(
        self,
        actor_scope: str,
        method: str,
        template: str,
        key: str,
        buffer: IdempotencyResponseBuffer,
    ) -> None:
        """
        Persist the cached response on the record; swallow (log) any store failure.

        Args:
            actor_scope (str): The resolved actor scope.
            method (str): The request's HTTP method.
            template (str): The matched route TEMPLATE.
            key (str): The client-supplied idempotency key.
            buffer (IdempotencyResponseBuffer): The buffered response to cache.
        """
        # 1. Cache is best-effort: the client's response is already decided, so a store error must not
        #    surface — it merely means a retry re-runs instead of replaying (still correct, less optimal).
        try:
            await CONTEXT.database.idempotency.complete(
                actor_scope=actor_scope,
                method=method,
                path=template,
                idempotency_key=key,
                response_status=buffer.status or 200,
                response_body=buffer.body,
                response_media_type=buffer.media_type,
                completed_at=datetime.now(UTC),
            )
        except Exception as error:
            logger.warning(
                f"Idempotency complete failed (swallowed) for {method} {template}: {error}"
            )

    async def _safe_drop(self, actor_scope: str, method: str, template: str, key: str) -> None:
        """
        Delete the in-progress record so a retry re-runs; swallow (log) any store failure.

        Args:
            actor_scope (str): The resolved actor scope.
            method (str): The request's HTTP method.
            template (str): The matched route TEMPLATE.
            key (str): The client-supplied idempotency key.
        """
        # 1. Best-effort drop: on failure the stale in-progress row simply 409s a retry until it
        #    expires and the GC prunes it — never a correctness problem, so the error is swallowed.
        try:
            await CONTEXT.database.idempotency.delete(
                actor_scope=actor_scope, method=method, path=template, idempotency_key=key
            )
        except Exception as error:
            logger.warning(f"Idempotency drop failed (swallowed) for {method} {template}: {error}")

    @staticmethod
    def _header(scope: Scope, name: bytes) -> str | None:
        """
        Read one header value from the raw ASGI header list (case-insensitive byte match).

        Args:
            scope (Scope): The ASGI connection scope.
            name (bytes): The lower-case header name to look up.

        Returns:
            str | None: The decoded, stripped header value, or None when absent or blank.
        """
        # 1. ASGI headers are a list of lower-cased (name, value) byte tuples.
        for header_name, header_value in scope.get("headers", []):
            if header_name == name:
                value = header_value.decode("latin-1").strip()
                return value or None
        return None


__all__ = ["IdempotencyMiddleware"]
