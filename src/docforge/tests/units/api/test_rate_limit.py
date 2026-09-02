# ====== Code Summary ======
# Unit coverage for the in-app rate limiter: the pure exemption policy + bucket keying (identity vs
# IP, X-Forwarded-For), plus end-to-end middleware behaviour through the real app (disabled → never
# limits; enabled → 429 after N; the exempt job subtree → never limited). Auth is off for the suite,
# so the integration path exercises IP keying; identity keying is covered by the pure keying test.

# ====== Standard Library Imports ======
import uuid


# ─────────────────────────── Pure: exemption policy ───────────────────────────
def test_exemptions_only_api_v1_limited_minus_jobs_subtree() -> None:
    """Only /api/v1/* is limited, and the whole job-monitoring subtree is exempt."""
    from backend.libs.ratelimit import RateLimitExemptions  # noqa: PLC0415

    # 1. Ordinary API routes are limited.
    assert RateLimitExemptions.is_limited("/api/v1/collections") is True
    assert RateLimitExemptions.is_limited("/api/v1/collections/abc/search") is True

    # 2. The job subtree (list, detail, SSE stream, queue/worker polls) is exempt.
    assert RateLimitExemptions.is_limited("/api/v1/jobs") is False
    assert RateLimitExemptions.is_limited("/api/v1/jobs/123") is False
    assert RateLimitExemptions.is_limited("/api/v1/jobs/123/stream") is False
    assert RateLimitExemptions.is_limited("/api/v1/jobs/queue") is False
    assert RateLimitExemptions.is_limited("/api/v1/jobs/workers/live") is False

    # 3. Everything outside /api/v1 (health, /metrics, docs, static UI) is inherently exempt.
    assert RateLimitExemptions.is_limited("/health") is False
    assert RateLimitExemptions.is_limited("/metrics") is False
    assert RateLimitExemptions.is_limited("/scalar") is False
    assert RateLimitExemptions.is_limited("/openapi.json") is False


# ─────────────────────────── Pure: bucket keying ───────────────────────────
def _scope(headers: list[tuple[bytes, bytes]] | None = None, client=("10.0.0.9", 5000)):
    """Build a minimal ASGI HTTP scope for the keying helper."""
    return {"type": "http", "headers": headers or [], "client": client}


def test_keying_uses_api_key_identity_when_authenticated() -> None:
    """An authenticated caller is keyed by its API key id, independent of IP."""
    from backend.libs.auth import AuthPrincipal  # noqa: PLC0415
    from backend.libs.ratelimit import RateLimitKeyResolver  # noqa: PLC0415

    key_id = uuid.uuid4()

    class _Key:
        id = key_id

    principal = AuthPrincipal(user=None, key=_Key(), is_full_access=True)
    key = RateLimitKeyResolver.resolve(_scope(), principal, trust_forwarded_for=True)
    assert key == f"key:{key_id}"


def test_keying_falls_back_to_client_ip_without_identity() -> None:
    """With no API key (auth off / synthetic root) the caller is keyed by client IP."""
    from backend.libs.auth import AuthPrincipal  # noqa: PLC0415
    from backend.libs.ratelimit import RateLimitKeyResolver  # noqa: PLC0415

    principal = AuthPrincipal.synthetic_root()
    key = RateLimitKeyResolver.resolve(_scope(client=("198.51.100.4", 40)), principal, True)
    assert key == "ip:198.51.100.4"


def test_keying_honours_leftmost_forwarded_for_when_trusted() -> None:
    """The leftmost X-Forwarded-For hop is the real client when the proxy is trusted."""
    from backend.libs.ratelimit import RateLimitKeyResolver  # noqa: PLC0415

    scope = _scope(headers=[(b"x-forwarded-for", b"203.0.113.7, 10.0.0.1")])
    assert RateLimitKeyResolver.resolve(scope, None, trust_forwarded_for=True) == "ip:203.0.113.7"


def test_keying_ignores_forwarded_for_when_untrusted() -> None:
    """When XFF is not trusted the transport peer address is used instead."""
    from backend.libs.ratelimit import RateLimitKeyResolver  # noqa: PLC0415

    scope = _scope(headers=[(b"x-forwarded-for", b"203.0.113.7")], client=("10.0.0.2", 9))
    assert RateLimitKeyResolver.resolve(scope, None, trust_forwarded_for=False) == "ip:10.0.0.2"


# ─────────────────────────── Integration: middleware ───────────────────────────
def test_disabled_never_limits(client, monkeypatch) -> None:
    """With RATE_LIMIT_ENABLED false (default), a limited route is never 429'd."""
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "RATE_LIMIT_ENABLED", False)
    headers = {"X-Forwarded-For": "203.0.113.20"}
    for _ in range(5):
        response = client.get("/api/v1/pipelines", headers=headers)
        assert response.status_code != 429


def test_enabled_returns_429_after_budget(client, monkeypatch) -> None:
    """With the limiter on and a budget of N, request N+1 from one caller gets 429 + Retry-After."""
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(RUNTIME_CONFIG, "RATE_LIMIT_PER_MINUTE", 2)
    # A unique client IP isolates this test's window from the shared in-process store.
    headers = {"X-Forwarded-For": "203.0.113.31"}

    first = client.get("/api/v1/pipelines", headers=headers)
    second = client.get("/api/v1/pipelines", headers=headers)
    third = client.get("/api/v1/pipelines", headers=headers)

    assert first.status_code != 429
    assert second.status_code != 429
    assert third.status_code == 429
    assert "Retry-After" in third.headers
    assert int(third.headers["Retry-After"]) >= 1


def test_exempt_job_subtree_never_limited(client, monkeypatch) -> None:
    """Even over budget, the job-poll subtree is exempt so the UI is never throttled."""
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(RUNTIME_CONFIG, "RATE_LIMIT_PER_MINUTE", 1)
    headers = {"X-Forwarded-For": "203.0.113.42"}
    # Hit the job detail route well past the budget — the limiter must not fire (DB errors are fine,
    # only 429 is asserted against).
    for _ in range(4):
        response = client.get(f"/api/v1/jobs/{uuid.uuid4()}", headers=headers)
        assert response.status_code != 429


def test_limiter_fails_open_on_storage_error(client, monkeypatch) -> None:
    """A limiter storage error must FAIL OPEN (allow + log), never surface as a 500 self-DoS."""
    from limits.aio.strategies import MovingWindowRateLimiter  # noqa: PLC0415

    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(RUNTIME_CONFIG, "RATE_LIMIT_PER_MINUTE", 1)

    async def _boom(*args, **kwargs):
        raise RuntimeError("rate-limit storage down")

    monkeypatch.setattr(MovingWindowRateLimiter, "hit", _boom)

    headers = {"X-Forwarded-For": "203.0.113.77"}
    # Even well past the budget, a broken limiter allows the request through (never 429, never 500).
    for _ in range(3):
        response = client.get("/api/v1/pipelines", headers=headers)
        assert response.status_code not in (429, 500)


def test_distinct_ips_have_independent_budgets(client, monkeypatch) -> None:
    """Two different client IPs get separate windows — one caller's flood never limits another."""
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(RUNTIME_CONFIG, "RATE_LIMIT_PER_MINUTE", 1)

    # Exhaust caller A's budget.
    a = {"X-Forwarded-For": "203.0.113.51"}
    assert client.get("/api/v1/pipelines", headers=a).status_code != 429
    assert client.get("/api/v1/pipelines", headers=a).status_code == 429

    # Caller B still has its full budget.
    b = {"X-Forwarded-For": "203.0.113.52"}
    assert client.get("/api/v1/pipelines", headers=b).status_code != 429
