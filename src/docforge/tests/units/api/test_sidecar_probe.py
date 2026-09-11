# ====== Code Summary ======
# Unit tests for SidecarProbe — the app-side reachability probe behind GET /capabilities. These pin the
# HONEST meaning of the `reachable` bit the endpoint reports, so a future edit cannot silently loosen it:
#   * reachable=True ONLY on a genuine HTTP 200 (deployed AND ready) — a readiness 503 reads NOT reachable;
#   * ANY connection-level failure (the exact prod `ConnectError: All connection attempts failed` a worker
#     hit when paddle_server restarted mid-parse) reads unreachable, never propagates as a 500;
#   * the whole result map is memoised for CACHE_TTL, so a burst of /capabilities calls costs ONE probe
#     round — but a fresh, ephemeral client is used per round (it re-resolves DNS, unlike a long-lived
#     worker pool), which is exactly why the app probe can read reachable while an in-flight worker call
#     to a just-restarted sidecar fails. The probe's `transport=` seam lets us assert all of this offline.
# `backend` imports are deferred into the test bodies: the api-dir autouse fixture boots the app (putting
# app/ on sys.path) before any body runs — a module-scope `backend` import would fail at collection time.

# ====== Standard Library Imports ======
import asyncio

# ====== Third-Party Library Imports ======
import httpx


def _run(coro):
    """Drive one coroutine to completion on a throwaway event loop (mirrors the sibling api tests)."""
    return asyncio.run(coro)


def test_reachable_only_on_a_ready_200_and_reads_advertised_device() -> None:
    """A ready 200 with a device body → reachable=True + the advertised device, no detail note."""
    from backend.libs.capabilities.probe import SidecarProbe  # noqa: PLC0415 — deferred

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "ok", "ready": True, "device": "cuda"})

    probe = SidecarProbe(
        timeout_seconds=0.5, cache_ttl_seconds=10.0, transport=httpx.MockTransport(handler)
    )
    results = _run(probe.probe({"bge_server": "http://bge_server:80"}))

    assert results["bge_server"].reachable is True
    assert results["bge_server"].device == "cuda"
    assert results["bge_server"].detail is None


def test_readiness_503_is_reported_reachable_false_not_ready() -> None:
    """A sidecar still loading answers 503 → NOT reachable, with a 'not ready' detail (never a crash)."""
    from backend.libs.capabilities.probe import SidecarProbe  # noqa: PLC0415 — deferred

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"status": "loading", "ready": False})

    probe = SidecarProbe(
        timeout_seconds=0.5, cache_ttl_seconds=10.0, transport=httpx.MockTransport(handler)
    )
    result = _run(probe.probe({"paddle_server": "http://paddle_server:80"}))["paddle_server"]

    assert result.reachable is False
    assert result.detail is not None and "not ready" in result.detail


def test_connect_error_reads_unreachable_and_never_propagates() -> None:
    """The exact prod failure — a mid-restart sidecar refusing connections — degrades to unreachable.

    This is the honesty boundary the /capabilities contract lives on: a connection-level error (the
    worker's `ConnectError: All connection attempts failed`) must read as unreachable, NEVER escape as
    a 500. It also documents WHY the app probe can read reachable while a worker parse fails: the probe
    opens a fresh connection here, so once the sidecar is back it succeeds — a long-lived worker pool
    reusing a dead connection is a separate, worker-side concern.
    """
    from backend.libs.capabilities.probe import SidecarProbe  # noqa: PLC0415 — deferred

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("All connection attempts failed", request=request)

    probe = SidecarProbe(
        timeout_seconds=0.5, cache_ttl_seconds=10.0, transport=httpx.MockTransport(handler)
    )
    result = _run(probe.probe({"paddle_server": "http://paddle_server:80"}))["paddle_server"]

    assert result.reachable is False
    assert result.device is None
    assert result.detail == "unreachable"


def test_result_map_is_memoised_within_the_ttl_then_refreshed() -> None:
    """A burst within the TTL costs ONE probe round; a zero TTL refreshes on every call."""
    from backend.libs.capabilities.probe import SidecarProbe  # noqa: PLC0415 — deferred

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"ready": True})

    targets = {"gotenberg": "http://gotenberg:3000"}

    # 1. Within the TTL, two consecutive probes reuse the cached round → the handler ran only once.
    cached = SidecarProbe(
        timeout_seconds=0.5, cache_ttl_seconds=60.0, transport=httpx.MockTransport(handler)
    )
    _run(cached.probe(targets))
    _run(cached.probe(targets))
    assert calls["n"] == 1

    # 2. A zero TTL disables the cache → each probe is a fresh round (re-resolving liveness read).
    calls["n"] = 0
    live = SidecarProbe(
        timeout_seconds=0.5, cache_ttl_seconds=0.0, transport=httpx.MockTransport(handler)
    )
    _run(live.probe(targets))
    _run(live.probe(targets))
    assert calls["n"] == 2
