# ====== Code Summary ======
# Correlation id coverage on the app side: RequestIdMiddleware mints an id, honours an inbound
# X-Request-ID / X-Correlation-ID, and echoes X-Request-ID on the response (including on a 401/429
# short-circuit, proving it sits OUTER to Auth + RateLimit); the id is bound into the shared
# ContextVar for the duration of a request; and QueueClient threads that ambient id onto the enqueued
# job as a NORMAL `correlation_id` task kwarg (not a reserved arq control kwarg — that would crash the
# task, as _job_timeout once did). Auth is off for the suite (see conftest), so 429 is reached by
# enabling the limiter; the id-on-401 case flips auth on for a single request.

# ====== Standard Library Imports ======
import re

# ====== Third-Party Library Imports ======
import fakeredis
from arq.constants import job_key_prefix
from arq.jobs import deserialize_job_raw

_HEX32 = re.compile(r"^[0-9a-f]{32}$")


# ─────────────────────────── Pure: inbound id resolution ───────────────────────────
def test_resolve_mints_a_fresh_id_when_no_header(fastapi_app) -> None:
    """With no honoured header, a fresh uuid4-hex id is minted."""
    from backend.libs.requestid import RequestIdHelpers  # noqa: PLC0415

    minted = RequestIdHelpers.resolve([])
    assert _HEX32.match(minted)


def test_resolve_honours_x_request_id(fastapi_app) -> None:
    """An inbound X-Request-ID is preserved verbatim (upstream proxy id kept end-to-end)."""
    from backend.libs.requestid import RequestIdHelpers  # noqa: PLC0415

    resolved = RequestIdHelpers.resolve([(b"x-request-id", b"upstream-abc-123")])
    assert resolved == "upstream-abc-123"


def test_resolve_accepts_x_correlation_id_alias(fastapi_app) -> None:
    """X-Correlation-ID is accepted as an alias when X-Request-ID is absent."""
    from backend.libs.requestid import RequestIdHelpers  # noqa: PLC0415

    resolved = RequestIdHelpers.resolve([(b"x-correlation-id", b"corr-77")])
    assert resolved == "corr-77"


def test_resolve_prefers_x_request_id_over_correlation(fastapi_app) -> None:
    """When both are present, X-Request-ID wins (it is the primary honoured header)."""
    from backend.libs.requestid import RequestIdHelpers  # noqa: PLC0415

    resolved = RequestIdHelpers.resolve(
        [(b"x-correlation-id", b"corr-77"), (b"x-request-id", b"req-9")]
    )
    assert resolved == "req-9"


def test_resolve_sanitises_header_injection_attempt(fastapi_app) -> None:
    """CR/LF and other unsafe bytes are stripped so the id can never split a header/log line."""
    from backend.libs.requestid import RequestIdHelpers  # noqa: PLC0415

    resolved = RequestIdHelpers.resolve([(b"x-request-id", b"abc\r\nSet-Cookie: x=1")])
    assert "\r" not in resolved and "\n" not in resolved
    assert resolved == "abcSet-Cookiex1"


def test_resolve_mints_when_inbound_is_all_unsafe(fastapi_app) -> None:
    """An inbound value that sanitises to empty falls back to a freshly minted id."""
    from backend.libs.requestid import RequestIdHelpers  # noqa: PLC0415

    resolved = RequestIdHelpers.resolve([(b"x-request-id", b"\r\n\r\n")])
    assert _HEX32.match(resolved)


# ─────────────────────────── Integration: response header ───────────────────────────
def test_response_carries_minted_request_id(client) -> None:
    """Every response echoes an X-Request-ID even when the request sent none."""
    response = client.get("/health")
    assert _HEX32.match(response.headers["x-request-id"])


def test_response_echoes_inbound_request_id(client) -> None:
    """An inbound X-Request-ID is echoed back unchanged (traceable round-trip)."""
    response = client.get("/health", headers={"X-Request-ID": "trace-me-42"})
    assert response.headers["x-request-id"] == "trace-me-42"


def test_response_honours_inbound_correlation_id_alias(client) -> None:
    """An inbound X-Correlation-ID is honoured and echoed on the X-Request-ID response header."""
    response = client.get("/health", headers={"X-Correlation-ID": "corr-abc"})
    assert response.headers["x-request-id"] == "corr-abc"


def test_id_survives_on_401_short_circuit(client, monkeypatch) -> None:
    """A 401 (auth on, no bearer) still carries the header — RequestId is OUTER to Auth."""
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)
    response = client.get("/api/v1/collections", headers={"X-Request-ID": "on-401"})
    assert response.status_code == 401
    assert response.headers["x-request-id"] == "on-401"


def test_id_survives_on_429_short_circuit(client, monkeypatch) -> None:
    """A 429 (limiter enabled, budget 0) still carries the header — RequestId is OUTER to RateLimit."""
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(RUNTIME_CONFIG, "RATE_LIMIT_PER_MINUTE", 0)
    response = client.get("/api/v1/collections", headers={"X-Request-ID": "on-429"})
    assert response.status_code == 429
    assert response.headers["x-request-id"] == "on-429"


# ─────────────────────────── ContextVar binding during a request ───────────────────────────
async def test_contextvar_is_bound_during_a_request(fastapi_app) -> None:
    """The middleware binds the inbound id into the shared ContextVar for the downstream app.

    Driven at the pure-ASGI layer (a stub downstream app) rather than through a route, because the
    real app mounts StaticFiles at ``/`` which would shadow any test route — this isolates the
    middleware's binding contract itself.
    """
    from backend.libs.requestid import RequestIdMiddleware  # noqa: PLC0415
    from shared_libs.observability import CorrelationContext  # noqa: PLC0415

    seen: dict[str, str | None] = {}

    async def _downstream(scope, receive, send) -> None:
        # The middleware bound the id BEFORE calling us — read it off the ContextVar.
        seen["cid"] = CorrelationContext.get()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    sent: list[dict] = []

    async def _send(message) -> None:
        sent.append(message)

    async def _receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {"type": "http", "path": "/x", "headers": [(b"x-request-id", b"in-flight-1")]}
    await RequestIdMiddleware(_downstream)(scope, _receive, _send)

    # 1. Bound while in flight, echoed on the response, and released afterwards.
    assert seen["cid"] == "in-flight-1"
    start = next(m for m in sent if m["type"] == "http.response.start")
    assert (b"x-request-id", b"in-flight-1") in start["headers"]
    assert CorrelationContext.get() is None


def test_contextvar_is_unbound_outside_any_request(fastapi_app) -> None:
    """Outside a request nothing is bound (the log patcher then renders the placeholder)."""
    from shared_libs.observability import CorrelationContext  # noqa: PLC0415

    assert CorrelationContext.get() is None


# ─────────────────────────── Enqueue threads the id as a normal task kwarg ───────────────────────────
async def _fake_pool():
    """A real ArqRedis wired onto an in-memory fakeredis backend."""
    from arq.connections import ArqRedis  # noqa: PLC0415

    fake = fakeredis.FakeAsyncRedis()
    return ArqRedis(connection_pool=fake.connection_pool), fake


async def _deserialize(fake, job_id: str) -> tuple[str, tuple, dict]:
    raw = await fake.get(job_key_prefix + job_id)
    function, args, kwargs, _job_try, _enqueue_time_ms = deserialize_job_raw(raw)
    return function, args, kwargs


async def test_enqueue_threads_correlation_id_as_normal_kwarg(fastapi_app) -> None:
    """A bound id rides the wire as a NORMAL `correlation_id` kwarg — arq did NOT treat it as control.

    If `correlation_id` were a reserved arq control kwarg (like `_expires`), arq would consume it and
    it would NOT appear in the serialized task kwargs. Its presence here proves it is a plain task
    argument — exactly what the worker's `with_correlation` wrapper consumes (and, unlike the shipped
    `_job_timeout` bug, one the task signature accepts, so it never crashes dispatch).
    """
    from backend.utils.queue import QueueClient  # noqa: PLC0415
    from shared_libs.observability import CorrelationContext  # noqa: PLC0415

    pool, fake = await _fake_pool()
    client = QueueClient("redis://localhost:6379")
    client._pool = pool
    token = CorrelationContext.set("enqueue-cid-1")
    try:
        await client.enqueue_ingest("doc-1", "job-1")
        (job_id,) = [key async for key in fake.scan_iter(job_key_prefix + "*")]
        function, args, kwargs = await _deserialize(
            fake, job_id.decode().removeprefix(job_key_prefix)
        )
        assert function == "ingest_document"
        assert args == ("doc-1", "job-1")
        assert kwargs == {"correlation_id": "enqueue-cid-1"}
    finally:
        CorrelationContext.reset(token)
        await fake.aclose()


async def test_enqueue_omits_kwarg_when_no_id_bound(fastapi_app) -> None:
    """With nothing bound the enqueue stays ids-only (the worker mints its own id) — no stray kwarg."""
    from backend.utils.queue import QueueClient  # noqa: PLC0415

    pool, fake = await _fake_pool()
    client = QueueClient("redis://localhost:6379")
    client._pool = pool
    try:
        await client.enqueue_ingest("doc-2", "job-2")
        (job_id,) = [key async for key in fake.scan_iter(job_key_prefix + "*")]
        _function, _args, kwargs = await _deserialize(
            fake, job_id.decode().removeprefix(job_key_prefix)
        )
        assert kwargs == {}
    finally:
        await fake.aclose()
