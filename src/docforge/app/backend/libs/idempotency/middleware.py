# ====== Code Summary ======
# IdempotencyMiddleware — a pure ASGI middleware giving DocForge Stripe-style idempotency on the small
# set of eligible mutating JSON endpoints. When IDEMPOTENCY_ENABLED and a mutating request to an
# eligible route carries an ``Idempotency-Key`` header, it: (1) fingerprints the body, (2) INSERTs an
# in-progress guard row (the UNIQUE constraint is the concurrency guard), (3a) if it WON the insert,
# runs the handler once, buffers the response, and — only for a definitive (< 500) outcome — caches it
# so retries replay it (a 5xx/exception drops the row so a retry re-runs), (3b) if the row already
# existed, replays the cached response (same key+body → the ORIGINAL cached status + body + content-type
# + an ``Idempotency-Replayed: true`` marker), or rejects a body mismatch (422) or an in-flight
# duplicate (409). NOTE: the replay restores the status, body and content-type only — other headers the
# handler set are NOT persisted today, so they are absent on a replay. Everything else is a transparent
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
from ..metrics import SCOPE_ROUTE_TEMPLATE
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

        # 3b. Hand the resolved template to the OUTER metrics middleware via the shared scope, so a
        #     replay/reject that short-circuits BEFORE routing is still attributed to its real endpoint
        #     (the router never sets scope["route"] on a short-circuit). Harmless on the execute path,
        #     where the router sets the real route and the metrics middleware prefers it.
        scope[SCOPE_ROUTE_TEMPLATE] = template

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

        # 3. The row already existed. A STALE in-progress guard (its owner crashed before caching a
        #    response) is atomically reclaimed so this retry re-runs instead of wedging on 409 until
        #    the TTL/GC; a genuinely in-flight (fresh) one still conflicts below.
        record = begin.record
        if self._is_stale_in_progress(record):
            reclaimed = await self._reclaim(
                scope, receive, send, actor_scope, template, key, fingerprint
            )
            if reclaimed:
                return
            # Lost the reclaim race (a concurrent retry claimed it, or it just completed) → re-read
            # the current incumbent so the normal path can replay a completion or 409 an in-flight one.
            record = await self._safe_get(actor_scope, scope["method"], template, key)

        # 4. Replay the cached response or reject the duplicate (409 in-progress / 422 body reuse).
        await self._replay_or_reject(scope, receive, send, record, fingerprint)

    def _is_stale_in_progress(self, record: IdempotencyRecord | None) -> bool:
        """
        Decide whether an existing record is a reclaimable stale in-progress guard.

        Args:
            record (IdempotencyRecord | None): The incumbent record from the lost-race read.

        Returns:
            bool: True only for an ``in_progress`` record whose start clock predates the in-progress
                TTL horizon (a fresh in-flight request, a completed record, a vanished row, or a row
                with no known start clock are all NOT reclaimable).
        """
        # 1. Only an in-progress record with a known start clock can be judged stale.
        if (
            record is None
            or record.state != IdempotencyState.in_progress
            or record.created_at is None
        ):
            return False
        # 2. Stale iff it started before the bounded in-progress window.
        cutoff = datetime.now(UTC) - timedelta(
            seconds=RUNTIME_CONFIG.IDEMPOTENCY_INPROGRESS_TTL_SECONDS
        )
        return record.created_at < cutoff

    async def _reclaim(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        actor_scope: str,
        template: str,
        key: str,
        fingerprint: str,
    ) -> bool:
        """
        Atomically claim a stale in-progress record and, on success, run the handler once.

        Args:
            scope (Scope): The ASGI connection scope.
            receive (Receive): The replay receive channel (re-feeds the buffered body).
            send (Send): The ASGI send channel.
            actor_scope (str): The resolved actor scope of the record.
            template (str): The matched route TEMPLATE.
            key (str): The client-supplied idempotency key.
            fingerprint (str): sha256 hex of THIS request's body (becomes the new owner's fingerprint).

        Returns:
            bool: True when this request won the claim and executed the handler; False when the claim
                was lost (the caller then re-reads + dispatches on the normal replay/reject path).
        """
        # 1. Try the atomic conditional claim (best-effort: a store error → treat as lost → 409/replay).
        now = datetime.now(UTC)
        try:
            won = await CONTEXT.database.idempotency.reclaim_stale(
                actor_scope=actor_scope,
                method=scope["method"],
                path=template,
                idempotency_key=key,
                request_fingerprint=fingerprint,
                expires_at=now + timedelta(hours=RUNTIME_CONFIG.IDEMPOTENCY_TTL_HOURS),
                claimed_at=now,
                stale_before=now
                - timedelta(seconds=RUNTIME_CONFIG.IDEMPOTENCY_INPROGRESS_TTL_SECONDS),
            )
        except Exception as error:
            logger.warning(
                f"Idempotency reclaim failed (swallowed) for {scope['method']} {template}: {error}"
            )
            return False

        # 2. Won the claim → run the handler exactly once, exactly like a fresh insert would.
        if won:
            await self._execute(scope, receive, send, actor_scope, template, key)
            return True
        return False

    async def _safe_get(
        self, actor_scope: str, method: str, template: str, key: str
    ) -> IdempotencyRecord | None:
        """
        Re-read the current record after a lost reclaim; swallow (log) any store failure.

        Args:
            actor_scope (str): The resolved actor scope.
            method (str): The request's HTTP method.
            template (str): The matched route TEMPLATE.
            key (str): The client-supplied idempotency key.

        Returns:
            IdempotencyRecord | None: The freshest record, or None on a read failure (→ treated as
                in-progress → 409 by the caller).
        """
        # 1. Best-effort point read — a failure degrades to 409 (never a correctness problem).
        try:
            return await CONTEXT.database.idempotency.get(
                actor_scope=actor_scope, method=method, path=template, idempotency_key=key
            )
        except Exception as error:
            logger.warning(
                f"Idempotency re-read failed (swallowed) for {method} {template}: {error}"
            )
            return None

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

        # 3. Cache only a definitive (< 500) outcome whose body fits the cache cap; a 5xx (transient)
        #    or an over-cap response drops the row so a retry re-runs rather than caching an error or
        #    bloating the store with unbounded bytes. Either way the buffered response is flushed below.
        status = buffer.status
        cacheable = (
            status is not None
            and status < _SERVER_ERROR_FLOOR
            and not buffer.exceeds(RUNTIME_CONFIG.IDEMPOTENCY_MAX_BODY_BYTES)
        )
        if cacheable:
            await self._safe_complete(actor_scope, scope["method"], template, key, buffer)
        else:
            if status is not None and status < _SERVER_ERROR_FLOOR:
                logger.warning(
                    f"Idempotency response over the cache cap "
                    f"({RUNTIME_CONFIG.IDEMPOTENCY_MAX_BODY_BYTES}B) on {scope['method']} {template}; "
                    f"not cached (a retry re-executes)."
                )
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

        # 3. Completed with the SAME body → replay the cached outcome: the ORIGINAL status, body and
        #    content-type, plus the replay marker. Only those three fields are persisted, so other
        #    headers the original handler set are NOT restored (a known fidelity limit — see the
        #    module docstring); the status, body and content-type are byte-exact.
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
