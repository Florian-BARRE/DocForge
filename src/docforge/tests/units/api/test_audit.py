"""Audit-trail coverage: the pure target parser + applicability/actor helpers, the AuditMiddleware
(records a mutation with the right actor/target/status/correlation, skips reads, is FAIL-SAFE — a
façade error never 500s the request — and honours AUDIT_ENABLED=false), and the root-only GET /audit
handler (403 for a scoped key, keyset pagination + filter passthrough for a full-access key) plus its
opaque cursor codec.

All store access is mocked via CONTEXT.database; ``from backend...`` imports are deferred until the
``fastapi_app`` fixture has registered app/ on sys.path (module-top imports would fail collection).
The middleware is driven at the pure-ASGI layer (a stub downstream) because the real app mounts
StaticFiles at ``/`` which would shadow a test route — this isolates the middleware contract itself.
"""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

COLL = "11111111-1111-1111-1111-111111111111"
KEY_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


@pytest.fixture(autouse=True)
def _audit_on_for_this_module(fastapi_app, monkeypatch):
    """This module IS the audit-path coverage, so it opts back INTO auditing.

    The api-suite conftest forces AUDIT_ENABLED off for hermeticity (so ordinary route tests never
    write a real audit row); the recording tests here mock ``audit.record`` and need the middleware
    enabled to exercise it. Runs after the conftest fixture, so this override wins; the explicit
    ``AUDIT_ENABLED=false`` passthrough test flips it back off in its own body.
    """
    from config import RUNTIME_CONFIG  # noqa: PLC0415 — deferred until app/ is on sys.path

    monkeypatch.setattr(RUNTIME_CONFIG, "AUDIT_ENABLED", True)


# ── shared fakes ────────────────────────────────────────────────────────────────────────────────


def _principal(*, permissions, user=None, key=None):
    """Build an AuthPrincipal directly (full access iff permissions is None)."""
    from backend.libs.auth.principal import AuthPrincipal  # noqa: PLC0415

    return AuthPrincipal(user=user, key=key, is_full_access=permissions is None)


def _full():
    """A full-access (root / NULL-permission) principal with a backing key + user."""
    key = SimpleNamespace(id=uuid.UUID(KEY_ID), name="root-key", permissions=None)
    user = SimpleNamespace(id=uuid.UUID(USER_ID), username="root")
    return _principal(permissions=None, user=user, key=key)


def _scoped():
    """A scoped key (not full access) → must be 403'd by the root-only audit endpoint."""
    key = SimpleNamespace(
        id=uuid.UUID(KEY_ID), name="scoped-key", permissions={"collections": [COLL]}
    )
    user = SimpleNamespace(id=uuid.UUID(USER_ID), username="tenant")
    return _principal(permissions={"collections": [COLL]}, user=user, key=key)


async def _drive_middleware(scope_overrides: dict, downstream_status: int = 200):
    """Run AuditMiddleware over a stub downstream and return the send messages captured."""
    from backend.libs.audit import AuditMiddleware  # noqa: PLC0415

    scope = {
        "type": "http",
        "method": "POST",
        "path": f"/api/v1/collections/{COLL}",
        "headers": [],
        "client": ("203.0.113.7", 5555),
        "state": {},
        **scope_overrides,
    }

    async def _downstream(scope, receive, send) -> None:
        await send({"type": "http.response.start", "status": downstream_status, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    sent: list[dict] = []

    async def _send(message) -> None:
        sent.append(message)

    async def _receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    await AuditMiddleware(_downstream)(scope, _receive, _send)
    return sent


# ── target parser (pure) ──────────────────────────────────────────────────────────────────────


def test_target_parse_collection_with_uuid(fastapi_app) -> None:
    from backend.libs.audit import AuditTargetParser  # noqa: PLC0415

    assert AuditTargetParser.parse(f"/api/v1/collections/{COLL}/export") == ("collection", COLL)


def test_target_parse_collection_create_has_no_id(fastapi_app) -> None:
    from backend.libs.audit import AuditTargetParser  # noqa: PLC0415

    assert AuditTargetParser.parse("/api/v1/collections") == ("collection", None)


def test_target_parse_import_subaction_is_not_an_id(fastapi_app) -> None:
    """A sub-action word ('import') is NOT a UUID → id stays None, type still recognised."""
    from backend.libs.audit import AuditTargetParser  # noqa: PLC0415

    assert AuditTargetParser.parse("/api/v1/collections/import") == ("collection", None)


def test_target_parse_document_reingest(fastapi_app) -> None:
    from backend.libs.audit import AuditTargetParser  # noqa: PLC0415

    doc = "99999999-9999-9999-9999-999999999999"
    assert AuditTargetParser.parse(f"/api/v1/documents/{doc}/reingest") == ("document", doc)


def test_target_parse_chunk_bulk_enabled_has_no_id(fastapi_app) -> None:
    from backend.libs.audit import AuditTargetParser  # noqa: PLC0415

    assert AuditTargetParser.parse("/api/v1/chunks/enabled") == ("chunk", None)


def test_target_parse_job_cancel(fastapi_app) -> None:
    from backend.libs.audit import AuditTargetParser  # noqa: PLC0415

    job = "77777777-7777-7777-7777-777777777777"
    assert AuditTargetParser.parse(f"/api/v1/jobs/{job}/cancel") == ("job", job)


def test_target_parse_api_key_rotate(fastapi_app) -> None:
    from backend.libs.audit import AuditTargetParser  # noqa: PLC0415

    assert AuditTargetParser.parse(f"/api/v1/auth/keys/{KEY_ID}/rotate") == ("key", KEY_ID)


def test_target_parse_api_key_create_has_no_id(fastapi_app) -> None:
    from backend.libs.audit import AuditTargetParser  # noqa: PLC0415

    assert AuditTargetParser.parse("/api/v1/auth/keys") == ("key", None)


def test_target_parse_unrecognised_is_none(fastapi_app) -> None:
    from backend.libs.audit import AuditTargetParser  # noqa: PLC0415

    assert AuditTargetParser.parse("/api/v1/pipelines/x/edit") == (None, None)


# ── applicability + actor helpers (pure) ────────────────────────────────────────────────────────


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_is_auditable_mutating_api(fastapi_app, method) -> None:
    from backend.libs.audit import AuditHelpers  # noqa: PLC0415

    assert AuditHelpers.is_auditable(method, "/api/v1/collections") is True


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_is_auditable_skips_reads(fastapi_app, method) -> None:
    from backend.libs.audit import AuditHelpers  # noqa: PLC0415

    assert AuditHelpers.is_auditable(method, "/api/v1/collections") is False


def test_is_auditable_skips_non_api(fastapi_app) -> None:
    from backend.libs.audit import AuditHelpers  # noqa: PLC0415

    assert AuditHelpers.is_auditable("POST", "/metrics") is False


def test_actor_from_key_prefers_key_name(fastapi_app) -> None:
    from backend.libs.audit import AuditHelpers  # noqa: PLC0415

    actor = AuditHelpers.actor(_full())
    assert actor.key_id == uuid.UUID(KEY_ID)
    assert actor.user_id == uuid.UUID(USER_ID)
    assert actor.label == "root-key"


def test_actor_synthetic_root_when_no_rows(fastapi_app) -> None:
    from backend.libs.audit import AuditHelpers  # noqa: PLC0415

    actor = AuditHelpers.actor(_principal(permissions=None))  # user=None, key=None
    assert actor.key_id is None and actor.user_id is None and actor.label == "root"


def test_actor_none_principal_is_unattributed(fastapi_app) -> None:
    from backend.libs.audit import AuditHelpers  # noqa: PLC0415

    actor = AuditHelpers.actor(None)
    assert actor == actor.__class__(user_id=None, key_id=None, label=None)


# ── middleware ──────────────────────────────────────────────────────────────────────────────────


async def test_middleware_records_a_mutation(fastapi_app, monkeypatch) -> None:
    """A mutating /api/v1 request records one row with the right actor/target/status/correlation."""
    from backend.context import CONTEXT  # noqa: PLC0415
    from shared_libs.observability import CorrelationContext  # noqa: PLC0415

    record = AsyncMock()
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(audit=SimpleNamespace(record=record)))

    route = SimpleNamespace(path="/api/v1/collections/{collection_id}")
    token = CorrelationContext.set("cid-xyz")
    try:
        sent = await _drive_middleware(
            {"route": route, "state": {"principal": _full()}}, downstream_status=200
        )
    finally:
        CorrelationContext.reset(token)

    # 1. The response still flowed downstream untouched.
    assert any(m["type"] == "http.response.start" and m["status"] == 200 for m in sent)
    # 2. Exactly one row, carrying the template path (not the raw one), parsed target + real ip + cid.
    record.assert_awaited_once()
    kwargs = record.await_args.kwargs
    assert kwargs["method"] == "POST"
    assert kwargs["path"] == "/api/v1/collections/{collection_id}"
    assert kwargs["status_code"] == 200
    assert kwargs["target_type"] == "collection" and kwargs["target_id"] == COLL
    assert kwargs["actor_key_id"] == uuid.UUID(KEY_ID)
    assert kwargs["actor_label"] == "root-key"
    assert kwargs["correlation_id"] == "cid-xyz"
    assert kwargs["client_ip"] == "203.0.113.7"


async def test_middleware_records_final_status_on_4xx(fastapi_app, monkeypatch) -> None:
    """A routed 4xx is still recorded with its final status (audit is inner to Auth/RateLimit)."""
    from backend.context import CONTEXT  # noqa: PLC0415

    record = AsyncMock()
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(audit=SimpleNamespace(record=record)))

    route = SimpleNamespace(path="/api/v1/collections/{collection_id}")
    await _drive_middleware(
        {"route": route, "state": {"principal": _full()}}, downstream_status=404
    )

    assert record.await_args.kwargs["status_code"] == 404


async def test_middleware_skips_reads(fastapi_app, monkeypatch) -> None:
    """A GET is never recorded (transparent passthrough)."""
    from backend.context import CONTEXT  # noqa: PLC0415

    record = AsyncMock()
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(audit=SimpleNamespace(record=record)))

    await _drive_middleware({"method": "GET", "state": {"principal": _full()}})

    record.assert_not_awaited()


async def test_middleware_is_fail_safe(fastapi_app, monkeypatch) -> None:
    """A façade error is caught + swallowed — the user's request still completes (never a 500)."""
    from backend.context import CONTEXT  # noqa: PLC0415

    record = AsyncMock(side_effect=RuntimeError("db down"))
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(audit=SimpleNamespace(record=record)))

    route = SimpleNamespace(path="/api/v1/collections/{collection_id}")
    # No exception propagates, and the 200 the downstream sent still reached the client.
    sent = await _drive_middleware(
        {"route": route, "state": {"principal": _full()}}, downstream_status=200
    )

    assert any(m["type"] == "http.response.start" and m["status"] == 200 for m in sent)
    record.assert_awaited_once()


async def test_middleware_respects_disabled_flag(fastapi_app, monkeypatch) -> None:
    """With AUDIT_ENABLED=false the middleware is a transparent passthrough (no record)."""
    from backend.context import CONTEXT  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "AUDIT_ENABLED", False)
    record = AsyncMock()
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(audit=SimpleNamespace(record=record)))

    await _drive_middleware({"route": SimpleNamespace(path="/x"), "state": {"principal": _full()}})

    record.assert_not_awaited()


# ── cursor codec ────────────────────────────────────────────────────────────────────────────────


def test_cursor_roundtrip(fastapi_app) -> None:
    from backend.routers.audit.helpers import AuditReadHelpers  # noqa: PLC0415

    when = datetime(2026, 9, 1, 12, 30, 15, tzinfo=UTC)
    token = AuditReadHelpers.encode_cursor(when, 4242)
    assert AuditReadHelpers.decode_cursor(token) == (when, 4242)


def test_cursor_malformed_is_400(fastapi_app) -> None:
    from backend.routers.audit.helpers import AuditReadHelpers  # noqa: PLC0415

    with pytest.raises(HTTPException) as exc:
        AuditReadHelpers.decode_cursor("!!!not-base64!!!")
    assert exc.value.status_code == 400


# ── endpoint (root-only + pagination + filters) ─────────────────────────────────────────────────


def _row(row_id: int, when: datetime):
    """A stand-in AuditLog row carrying every field the AuditEntry mapper reads."""
    return SimpleNamespace(
        id=row_id,
        created_at=when,
        method="POST",
        path="/api/v1/collections/{collection_id}",
        status_code=200,
        actor_user_id=uuid.UUID(USER_ID),
        actor_key_id=uuid.UUID(KEY_ID),
        actor_label="root-key",
        target_type="collection",
        target_id=COLL,
        correlation_id="cid-1",
        client_ip="203.0.113.7",
    )


async def test_endpoint_scoped_key_is_403(fastapi_app) -> None:
    from backend.routers.audit.router import list_audit  # noqa: PLC0415

    with pytest.raises(HTTPException) as exc:
        await list_audit(
            limit=50,
            cursor=None,
            actor_user_id=None,
            actor_key_id=None,
            target_type=None,
            target_id=None,
            correlation_id=None,
            created_from=None,
            created_to=None,
            principal=_scoped(),
        )
    assert exc.value.status_code == 403


async def test_endpoint_paginates_and_sets_next_cursor(fastapi_app, monkeypatch) -> None:
    """Over-fetching one row → has_more → next_cursor seeded from the last KEPT row."""
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.audit.helpers import AuditReadHelpers  # noqa: PLC0415
    from backend.routers.audit.router import list_audit  # noqa: PLC0415

    when = datetime(2026, 9, 1, tzinfo=UTC)
    # limit=2 → the endpoint asks the façade for 3; return 3 to trigger has_more.
    rows = [_row(3, when), _row(2, when), _row(1, when)]
    list_mock = AsyncMock(return_value=rows)
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(audit=SimpleNamespace(list=list_mock)))

    page = await list_audit(
        limit=2,
        cursor=None,
        actor_user_id=None,
        actor_key_id=None,
        target_type=None,
        target_id=None,
        correlation_id=None,
        created_from=None,
        created_to=None,
        principal=_full(),
    )

    # 1. Over-fetch by one (limit+1) and trim to the page size.
    assert list_mock.await_args.kwargs["limit"] == 3
    assert [e.id for e in page.entries] == [3, 2]
    assert page.limit == 2
    # 2. next_cursor points at the last KEPT row (id=2), not the dropped sentinel (id=1).
    assert AuditReadHelpers.decode_cursor(page.next_cursor) == (when, 2)


async def test_endpoint_exhausted_has_null_cursor(fastapi_app, monkeypatch) -> None:
    """Fewer rows than limit+1 → the trail is exhausted → next_cursor is null."""
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.audit.router import list_audit  # noqa: PLC0415

    rows = [_row(2, datetime(2026, 9, 1, tzinfo=UTC))]
    list_mock = AsyncMock(return_value=rows)
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(audit=SimpleNamespace(list=list_mock)))

    page = await list_audit(
        limit=50,
        cursor=None,
        actor_user_id=None,
        actor_key_id=None,
        target_type=None,
        target_id=None,
        correlation_id=None,
        created_from=None,
        created_to=None,
        principal=_full(),
    )
    assert page.next_cursor is None and len(page.entries) == 1


async def test_endpoint_threads_filters_and_cursor(fastapi_app, monkeypatch) -> None:
    """Every filter + the decoded cursor is passed through to the façade."""
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.audit.helpers import AuditReadHelpers  # noqa: PLC0415
    from backend.routers.audit.router import list_audit  # noqa: PLC0415

    when = datetime(2026, 8, 1, tzinfo=UTC)
    list_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(audit=SimpleNamespace(list=list_mock)))

    frm = datetime(2026, 7, 1, tzinfo=UTC)
    to = datetime(2026, 9, 1, tzinfo=UTC)
    await list_audit(
        limit=10,
        cursor=AuditReadHelpers.encode_cursor(when, 5),
        actor_user_id=uuid.UUID(USER_ID),
        actor_key_id=uuid.UUID(KEY_ID),
        target_type="collection",
        target_id=COLL,
        correlation_id="cid-1",
        created_from=frm,
        created_to=to,
        principal=_full(),
    )

    kwargs = list_mock.await_args.kwargs
    assert kwargs["cursor_created_at"] == when and kwargs["cursor_id"] == 5
    assert kwargs["actor_user_id"] == uuid.UUID(USER_ID)
    assert kwargs["actor_key_id"] == uuid.UUID(KEY_ID)
    assert kwargs["target_type"] == "collection" and kwargs["target_id"] == COLL
    assert kwargs["correlation_id"] == "cid-1"
    assert kwargs["created_from"] == frm and kwargs["created_to"] == to


async def test_endpoint_clamps_limit(fastapi_app, monkeypatch) -> None:
    """A limit above AUDIT_MAX_PAGE_SIZE is clamped down (never an unbounded scan)."""
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.audit.router import list_audit  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "AUDIT_MAX_PAGE_SIZE", 25)
    list_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(audit=SimpleNamespace(list=list_mock)))

    page = await list_audit(
        limit=10_000,
        cursor=None,
        actor_user_id=None,
        actor_key_id=None,
        target_type=None,
        target_id=None,
        correlation_id=None,
        created_from=None,
        created_to=None,
        principal=_full(),
    )
    assert page.limit == 25
    assert list_mock.await_args.kwargs["limit"] == 26  # clamped 25 + 1 over-fetch
