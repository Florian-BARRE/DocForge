"""Idempotency coverage: the pure eligibility matcher + actor-scope resolver, and the
IdempotencyMiddleware driven at the pure-ASGI layer (a stub downstream). The middleware contract:
a new key runs the handler once + caches a definitive response; a retry with the same key+body
replays the cached bytes WITHOUT re-invoking the handler (+ ``Idempotency-Replayed`` header); a same
key with a different body is 422; an in-progress duplicate is 409; a 5xx / exception is NOT cached
(the guard row is dropped so a retry re-runs); an ineligible route / missing header / over-cap body
is a transparent passthrough; and a normal (non-replayed) request still sees its full body via the
re-fed receive channel.

All store access is mocked via CONTEXT.database.idempotency; ``from backend...`` imports are deferred
until the ``fastapi_app`` fixture has registered app/ on sys.path (module-top imports fail collection).
"""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

KEY_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
_BODY = b'{"name":"docs"}'
_KEY = "idem-key-123"


# ── principals / records ──────────────────────────────────────────────────────────────────────


def _principal(*, user=None, key=None):
    from backend.libs.auth.principal import AuthPrincipal  # noqa: PLC0415

    return AuthPrincipal(user=user, key=key, is_full_access=key is None)


def _full():
    """A key-backed principal → actor scope 'key:<uuid>'."""
    key = SimpleNamespace(id=uuid.UUID(KEY_ID), name="root-key", permissions=None)
    user = SimpleNamespace(id=uuid.UUID(USER_ID), username="root")
    return _principal(user=user, key=key)


def _record(*, state, fingerprint, status=None, body=None, media_type=None, created_at=None):
    from shared_libs.services.db.facades import IdempotencyRecord  # noqa: PLC0415

    return IdempotencyRecord(
        state=state,
        request_fingerprint=fingerprint,
        response_status=status,
        response_body=body,
        response_media_type=media_type,
        created_at=created_at,
    )


def _begin(*, created, record):
    from shared_libs.services.db.facades import IdempotencyBegin  # noqa: PLC0415

    return IdempotencyBegin(created=created, record=record)


def _fingerprint(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


# ── ASGI driver ─────────────────────────────────────────────────────────────────────────────────


async def _drive(
    *,
    monkeypatch,
    idempotency,
    scope_overrides=None,
    body=_BODY,
    downstream_status=201,
    downstream_body=b'{"ok":true}',
    raises: Exception | None = None,
):
    """Run IdempotencyMiddleware over a body-reading stub downstream; return (sent, state)."""
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.libs.idempotency import IdempotencyMiddleware  # noqa: PLC0415

    # monkeypatch (not a bare assignment) so the shared session-scoped CONTEXT is restored per test.
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(idempotency=idempotency))

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/collections",
        "headers": [(b"idempotency-key", _KEY.encode())],
        "client": ("203.0.113.7", 5555),
        "state": {"principal": _full()},
        **(scope_overrides or {}),
    }

    state = {"handler_called": False, "handler_body": None}

    async def _downstream(scope, receive, send) -> None:
        # Fully drain the (re-fed) body so we can assert the handler sees it intact.
        chunks: list[bytes] = []
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        state["handler_called"] = True
        state["handler_body"] = b"".join(chunks)
        if raises is not None:
            raise raises
        await send(
            {
                "type": "http.response.start",
                "status": downstream_status,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": downstream_body, "more_body": False})

    sent: list[dict] = []

    async def _send(message) -> None:
        sent.append(message)

    pending = iter([{"type": "http.request", "body": body, "more_body": False}])

    async def _receive() -> dict:
        try:
            return next(pending)
        except StopIteration:
            return {"type": "http.request", "body": b"", "more_body": False}

    await IdempotencyMiddleware(_downstream)(scope, _receive, _send)
    return sent, state


def _status_of(sent: list[dict]) -> int | None:
    for message in sent:
        if message["type"] == "http.response.start":
            return message["status"]
    return None


def _headers_of(sent: list[dict]) -> dict[bytes, bytes]:
    for message in sent:
        if message["type"] == "http.response.start":
            return dict(message.get("headers", []))
    return {}


def _body_of(sent: list[dict]) -> bytes:
    return b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")


# ── eligibility matcher (pure) ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "method,path,expected",
    [
        ("POST", "/api/v1/collections", "/api/v1/collections"),
        (
            "PATCH",
            "/api/v1/collections/11111111-1111-1111-1111-111111111111",
            "/api/v1/collections/{collection_id}",
        ),
        (
            "POST",
            "/api/v1/collections/abc/reingest",
            "/api/v1/collections/{collection_id}/reingest",
        ),
        (
            "POST",
            "/api/v1/collections/abc/documents/reingest",
            "/api/v1/collections/{collection_id}/documents/reingest",
        ),
        (
            "POST",
            "/api/v1/collections/abc/export",
            "/api/v1/collections/{collection_id}/export",
        ),
    ],
)
def test_eligibility_matches_template(fastapi_app, method, path, expected) -> None:
    from backend.libs.idempotency import IdempotencyEligibility  # noqa: PLC0415

    assert IdempotencyEligibility.match(method, path) == expected


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/v1/collections"),  # a read is never eligible
        ("POST", "/api/v1/documents"),  # the multipart upload is EXCLUDED
        ("POST", "/api/v1/collections/import"),  # the bundle upload is EXCLUDED
        ("POST", "/api/v1/auth/keys"),  # EXCLUDED: response carries the one-time plaintext key
        ("POST", "/api/v1/auth/keys/xyz/rotate"),  # EXCLUDED: same — secret must not be cached
        ("DELETE", "/api/v1/collections/abc"),  # delete is not in the allow-list
        ("POST", "/api/v1/collections/abc/search"),  # search is not a guarded trigger
    ],
)
def test_eligibility_rejects_non_allowlisted(fastapi_app, method, path) -> None:
    from backend.libs.idempotency import IdempotencyEligibility  # noqa: PLC0415

    assert IdempotencyEligibility.match(method, path) is None


# ── actor-scope resolver (pure) ───────────────────────────────────────────────────────────────


def test_actor_scope_prefers_key(fastapi_app) -> None:
    from backend.libs.idempotency import IdempotencyActorScope  # noqa: PLC0415

    assert IdempotencyActorScope.resolve(_full()) == f"key:{KEY_ID}"


def test_actor_scope_user_without_key(fastapi_app) -> None:
    from backend.libs.idempotency import IdempotencyActorScope  # noqa: PLC0415

    user = SimpleNamespace(id=uuid.UUID(USER_ID), username="u")
    assert IdempotencyActorScope.resolve(_principal(user=user)) == f"user:{USER_ID}"


def test_actor_scope_anon_when_no_identity(fastapi_app) -> None:
    from backend.libs.idempotency import IdempotencyActorScope  # noqa: PLC0415

    assert IdempotencyActorScope.resolve(_principal()) == "anon"
    assert IdempotencyActorScope.resolve(None) == "anon"


# ── middleware: first request runs once + caches ────────────────────────────────────────────────


async def test_new_key_runs_once_and_caches(fastapi_app, monkeypatch) -> None:
    """A first keyed request runs the handler once, its body is re-fed intact, and a 201 is cached."""
    from shared_libs.services.db.postgresql.tables import IdempotencyState  # noqa: PLC0415

    idempotency = SimpleNamespace(
        begin=AsyncMock(
            return_value=_begin(
                created=True,
                record=_record(state=IdempotencyState.in_progress, fingerprint=_fingerprint(_BODY)),
            )
        ),
        complete=AsyncMock(),
        delete=AsyncMock(),
    )

    sent, state = await _drive(
        monkeypatch=monkeypatch, idempotency=idempotency, downstream_status=201
    )

    # 1. The handler ran exactly once and saw the FULL request body (the ASGI re-feed works).
    assert state["handler_called"] is True
    assert state["handler_body"] == _BODY
    # 2. The response flowed to the client, and the definitive 201 was cached (not dropped).
    assert _status_of(sent) == 201
    idempotency.complete.assert_awaited_once()
    idempotency.delete.assert_not_awaited()
    kwargs = idempotency.complete.await_args.kwargs
    assert kwargs["response_status"] == 201
    assert kwargs["response_body"] == b'{"ok":true}'
    assert kwargs["response_media_type"] == "application/json"
    assert kwargs["path"] == "/api/v1/collections"
    assert kwargs["idempotency_key"] == _KEY
    assert kwargs["actor_scope"] == f"key:{KEY_ID}"


# ── middleware: replay ──────────────────────────────────────────────────────────────────────────


async def test_replay_same_key_and_body(fastapi_app, monkeypatch) -> None:
    """A retry with the same key+body replays the cached response and never re-invokes the handler."""
    from shared_libs.services.db.postgresql.tables import IdempotencyState  # noqa: PLC0415

    cached = _record(
        state=IdempotencyState.completed,
        fingerprint=_fingerprint(_BODY),
        status=201,
        body=b'{"cached":true}',
        media_type="application/json",
    )
    idempotency = SimpleNamespace(
        begin=AsyncMock(return_value=_begin(created=False, record=cached)),
        complete=AsyncMock(),
        delete=AsyncMock(),
    )

    sent, state = await _drive(monkeypatch=monkeypatch, idempotency=idempotency)

    # 1. The handler was NOT called — the cached bytes are served verbatim.
    assert state["handler_called"] is False
    assert _status_of(sent) == 201
    assert _body_of(sent) == b'{"cached":true}'
    # 2. The replay marker is present, and no cache write happened.
    assert _headers_of(sent).get(b"idempotency-replayed") == b"true"
    idempotency.complete.assert_not_awaited()


async def test_same_key_different_body_is_422(fastapi_app, monkeypatch) -> None:
    """A completed record whose fingerprint differs → key reused with a different body → 422."""
    from shared_libs.services.db.postgresql.tables import IdempotencyState  # noqa: PLC0415

    cached = _record(
        state=IdempotencyState.completed,
        fingerprint=_fingerprint(b"a-totally-different-body"),
        status=201,
        body=b"{}",
        media_type="application/json",
    )
    idempotency = SimpleNamespace(
        begin=AsyncMock(return_value=_begin(created=False, record=cached)),
        complete=AsyncMock(),
        delete=AsyncMock(),
    )

    sent, state = await _drive(monkeypatch=monkeypatch, idempotency=idempotency)

    assert state["handler_called"] is False
    assert _status_of(sent) == 422


async def test_in_progress_duplicate_is_409(fastapi_app, monkeypatch) -> None:
    """A still-in-progress record (a concurrent first request) → 409, retry later."""
    from shared_libs.services.db.postgresql.tables import IdempotencyState  # noqa: PLC0415

    in_flight = _record(state=IdempotencyState.in_progress, fingerprint=_fingerprint(_BODY))
    idempotency = SimpleNamespace(
        begin=AsyncMock(return_value=_begin(created=False, record=in_flight)),
        complete=AsyncMock(),
        delete=AsyncMock(),
    )

    sent, state = await _drive(monkeypatch=monkeypatch, idempotency=idempotency)

    assert state["handler_called"] is False
    assert _status_of(sent) == 409


async def test_vanished_record_is_409(fastapi_app, monkeypatch) -> None:
    """A lost-race insert whose incumbent row vanished before the read → treated as in-progress (409)."""
    idempotency = SimpleNamespace(
        begin=AsyncMock(return_value=_begin(created=False, record=None)),
        complete=AsyncMock(),
        delete=AsyncMock(),
    )

    sent, state = await _drive(monkeypatch=monkeypatch, idempotency=idempotency)

    assert state["handler_called"] is False
    assert _status_of(sent) == 409


# ── middleware: stale in-progress reclaim (crashed original execution) ─────────────────────────────


async def test_stale_in_progress_is_reclaimed_and_reruns(fastapi_app, monkeypatch) -> None:
    """A stale in-progress guard (owner crashed pre-cache) is reclaimed → the retry re-runs + caches."""
    from shared_libs.services.db.postgresql.tables import IdempotencyState  # noqa: PLC0415

    stale = _record(
        state=IdempotencyState.in_progress,
        fingerprint=_fingerprint(_BODY),
        created_at=datetime.now(UTC) - timedelta(hours=1),  # far older than the in-progress TTL
    )
    idempotency = SimpleNamespace(
        begin=AsyncMock(return_value=_begin(created=False, record=stale)),
        reclaim_stale=AsyncMock(return_value=True),  # this retry wins the atomic claim
        get=AsyncMock(),
        complete=AsyncMock(),
        delete=AsyncMock(),
    )

    sent, state = await _drive(
        monkeypatch=monkeypatch, idempotency=idempotency, downstream_status=201
    )

    # 1. The stale guard was atomically reclaimed and the handler ran once with the full body.
    idempotency.reclaim_stale.assert_awaited_once()
    assert state["handler_called"] is True
    assert state["handler_body"] == _BODY
    # 2. The definitive 201 flowed to the client and was cached (a normal execution after reclaim).
    assert _status_of(sent) == 201
    idempotency.complete.assert_awaited_once()


async def test_fresh_in_progress_is_not_reclaimed(fastapi_app, monkeypatch) -> None:
    """A fresh in-flight guard (within the in-progress TTL) still 409s — never reclaimed/re-run."""
    from shared_libs.services.db.postgresql.tables import IdempotencyState  # noqa: PLC0415

    fresh = _record(
        state=IdempotencyState.in_progress,
        fingerprint=_fingerprint(_BODY),
        created_at=datetime.now(UTC),  # brand new → genuinely in flight
    )
    idempotency = SimpleNamespace(
        begin=AsyncMock(return_value=_begin(created=False, record=fresh)),
        reclaim_stale=AsyncMock(return_value=True),
        get=AsyncMock(),
        complete=AsyncMock(),
        delete=AsyncMock(),
    )

    sent, state = await _drive(monkeypatch=monkeypatch, idempotency=idempotency)

    # 1. Staleness never triggered → no reclaim attempt, handler never ran, plain 409.
    idempotency.reclaim_stale.assert_not_awaited()
    assert state["handler_called"] is False
    assert _status_of(sent) == 409


async def test_lost_reclaim_race_falls_back_to_replay(fastapi_app, monkeypatch) -> None:
    """Losing the reclaim race re-reads the incumbent: a now-completed record replays its cache."""
    from shared_libs.services.db.postgresql.tables import IdempotencyState  # noqa: PLC0415

    stale = _record(
        state=IdempotencyState.in_progress,
        fingerprint=_fingerprint(_BODY),
        created_at=datetime.now(UTC) - timedelta(hours=1),
    )
    completed = _record(
        state=IdempotencyState.completed,
        fingerprint=_fingerprint(_BODY),
        status=201,
        body=b'{"cached":true}',
        media_type="application/json",
    )
    idempotency = SimpleNamespace(
        begin=AsyncMock(return_value=_begin(created=False, record=stale)),
        reclaim_stale=AsyncMock(return_value=False),  # a concurrent retry won the claim
        get=AsyncMock(return_value=completed),  # re-read shows it completed meanwhile
        complete=AsyncMock(),
        delete=AsyncMock(),
    )

    sent, state = await _drive(monkeypatch=monkeypatch, idempotency=idempotency)

    # 1. Reclaim lost → re-read → the completed record replays verbatim without re-running the handler.
    idempotency.reclaim_stale.assert_awaited_once()
    idempotency.get.assert_awaited_once()
    assert state["handler_called"] is False
    assert _status_of(sent) == 201
    assert _body_of(sent) == b'{"cached":true}'
    assert _headers_of(sent).get(b"idempotency-replayed") == b"true"


# ── middleware: not cached on failure ───────────────────────────────────────────────────────────


async def test_5xx_is_not_cached(fastapi_app, monkeypatch) -> None:
    """A 5xx is transient → the guard row is dropped (not completed) so a retry re-runs."""
    from shared_libs.services.db.postgresql.tables import IdempotencyState  # noqa: PLC0415

    idempotency = SimpleNamespace(
        begin=AsyncMock(
            return_value=_begin(
                created=True,
                record=_record(state=IdempotencyState.in_progress, fingerprint=_fingerprint(_BODY)),
            )
        ),
        complete=AsyncMock(),
        delete=AsyncMock(),
    )

    sent, state = await _drive(
        monkeypatch=monkeypatch, idempotency=idempotency, downstream_status=500
    )

    assert state["handler_called"] is True
    assert _status_of(sent) == 500  # the 5xx still reaches the client
    idempotency.complete.assert_not_awaited()
    idempotency.delete.assert_awaited_once()


async def test_handler_exception_drops_row_and_propagates(fastapi_app, monkeypatch) -> None:
    """A raising handler → the guard row is dropped and the exception propagates (nothing cached)."""
    from shared_libs.services.db.postgresql.tables import IdempotencyState  # noqa: PLC0415

    idempotency = SimpleNamespace(
        begin=AsyncMock(
            return_value=_begin(
                created=True,
                record=_record(state=IdempotencyState.in_progress, fingerprint=_fingerprint(_BODY)),
            )
        ),
        complete=AsyncMock(),
        delete=AsyncMock(),
    )

    with pytest.raises(RuntimeError):
        await _drive(monkeypatch=monkeypatch, idempotency=idempotency, raises=RuntimeError("boom"))

    idempotency.complete.assert_not_awaited()
    idempotency.delete.assert_awaited_once()


async def test_over_cap_response_is_not_cached(fastapi_app, monkeypatch) -> None:
    """A definitive response whose body exceeds the cap is served but NOT cached → the row is dropped."""
    from config import RUNTIME_CONFIG  # noqa: PLC0415
    from shared_libs.services.db.postgresql.tables import IdempotencyState  # noqa: PLC0415

    # Cap above the (tiny) request body but below the response body: the request is guarded normally,
    # only the response caching is what the cap must veto.
    monkeypatch.setattr(RUNTIME_CONFIG, "IDEMPOTENCY_MAX_BODY_BYTES", 20)
    big_response = b"x" * 100
    idempotency = SimpleNamespace(
        begin=AsyncMock(
            return_value=_begin(
                created=True,
                record=_record(state=IdempotencyState.in_progress, fingerprint=_fingerprint(b"{}")),
            )
        ),
        complete=AsyncMock(),
        delete=AsyncMock(),
    )

    sent, state = await _drive(
        monkeypatch=monkeypatch,
        idempotency=idempotency,
        body=b"{}",
        downstream_status=201,
        downstream_body=big_response,
    )

    # 1. The full (over-cap) response still reached the client verbatim.
    assert state["handler_called"] is True
    assert _status_of(sent) == 201
    assert _body_of(sent) == big_response
    # 2. It was NOT cached (over cap) — the guard row is dropped so a retry re-executes.
    idempotency.complete.assert_not_awaited()
    idempotency.delete.assert_awaited_once()


async def test_under_cap_response_is_cached(fastapi_app, monkeypatch) -> None:
    """A definitive response within the cap is cached for replay (the counterpart of the over-cap case)."""
    from config import RUNTIME_CONFIG  # noqa: PLC0415
    from shared_libs.services.db.postgresql.tables import IdempotencyState  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "IDEMPOTENCY_MAX_BODY_BYTES", 1024)
    idempotency = SimpleNamespace(
        begin=AsyncMock(
            return_value=_begin(
                created=True,
                record=_record(state=IdempotencyState.in_progress, fingerprint=_fingerprint(b"{}")),
            )
        ),
        complete=AsyncMock(),
        delete=AsyncMock(),
    )

    sent, state = await _drive(
        monkeypatch=monkeypatch,
        idempotency=idempotency,
        body=b"{}",
        downstream_status=201,
        downstream_body=b'{"ok":true}',
    )

    assert _status_of(sent) == 201
    idempotency.complete.assert_awaited_once()
    idempotency.delete.assert_not_awaited()


# ── middleware: passthrough paths ─────────────────────────────────────────────────────────────


async def test_ineligible_route_passthrough(fastapi_app, monkeypatch) -> None:
    """A mutating request on a non-allow-listed route never touches the store (transparent)."""
    idempotency = SimpleNamespace(begin=AsyncMock(), complete=AsyncMock(), delete=AsyncMock())

    sent, state = await _drive(
        monkeypatch=monkeypatch,
        idempotency=idempotency,
        scope_overrides={"path": "/api/v1/documents"},
    )

    idempotency.begin.assert_not_awaited()
    assert state["handler_called"] is True
    assert _status_of(sent) == 201


async def test_missing_header_passthrough(fastapi_app, monkeypatch) -> None:
    """No Idempotency-Key header → transparent passthrough (opt-in per request)."""
    idempotency = SimpleNamespace(begin=AsyncMock(), complete=AsyncMock(), delete=AsyncMock())

    sent, state = await _drive(
        monkeypatch=monkeypatch, idempotency=idempotency, scope_overrides={"headers": []}
    )

    idempotency.begin.assert_not_awaited()
    assert state["handler_called"] is True


async def test_disabled_flag_passthrough(fastapi_app, monkeypatch) -> None:
    """IDEMPOTENCY_ENABLED=false → transparent passthrough."""
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "IDEMPOTENCY_ENABLED", False)
    idempotency = SimpleNamespace(begin=AsyncMock(), complete=AsyncMock(), delete=AsyncMock())

    sent, state = await _drive(monkeypatch=monkeypatch, idempotency=idempotency)

    idempotency.begin.assert_not_awaited()
    assert state["handler_called"] is True


async def test_over_cap_body_skips_idempotency(fastapi_app, monkeypatch) -> None:
    """An eligible body over the buffer cap SKIPS idempotency and streams the full body through."""
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "IDEMPOTENCY_MAX_BODY_BYTES", 4)
    big_body = b'{"name":"a-body-well-over-four-bytes"}'
    idempotency = SimpleNamespace(begin=AsyncMock(), complete=AsyncMock(), delete=AsyncMock())

    sent, state = await _drive(monkeypatch=monkeypatch, idempotency=idempotency, body=big_body)

    # 1. The store was never touched, and the handler saw the FULL body (nothing dropped/truncated).
    idempotency.begin.assert_not_awaited()
    assert state["handler_called"] is True
    assert state["handler_body"] == big_body
