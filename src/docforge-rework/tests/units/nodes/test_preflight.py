"""Per-node preflight() reachability — the honest fail-fast-before-spend hook.

Covers the shared EndpointReachability probe's narrow semantics (connection failure fatal, 401/403
fatal, any other status = reachable) and that the base node's preflight() is a no-op. The runner
sweep (collect all action nodes → probe concurrently → fail fast before execute) is exercised live.
"""

import httpx
import pytest

from shared_libs.pipelines.ingest.nodes.enrich.figure_entry import (
    FigureEntryConfig,
    FigureEntryNode,
)
from shared_libs.pipelines.nodes.openai_compat.preflight import (
    EndpointReachability,
    PreflightError,
)


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def _fake_client(*, status_code: int | None = None, raises: Exception | None = None):
    """A stand-in for httpx.AsyncClient: an async context manager whose .get() answers or raises."""

    class _Client:
        def __init__(self, *args: object, **kwargs: object) -> None: ...

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *exc: object) -> None: ...

        async def get(self, url: str, headers: dict | None = None) -> _FakeResponse:
            if raises is not None:
                raise raises
            return _FakeResponse(status_code)

    return _Client


async def test_reachable_endpoint_passes(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(status_code=200))
    # No raise = reachable.
    await EndpointReachability.check(node_kind="llm", base_url="http://x:8000")


async def test_any_non_auth_status_is_reachable(monkeypatch) -> None:
    # A 404 on /models still means the host ANSWERED — reachable, must pass (no false positive).
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(status_code=404))
    await EndpointReachability.check(node_kind="vlm", base_url="http://x:8000")


async def test_rejected_credentials_401_is_fatal(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(status_code=401))
    with pytest.raises(PreflightError, match="credentials rejected"):
        await EndpointReachability.check(node_kind="llm", base_url="http://x:8000", api_key="k")


async def test_forbidden_403_is_fatal(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(status_code=403))
    with pytest.raises(PreflightError, match="credentials rejected"):
        await EndpointReachability.check(node_kind="embed", base_url="http://x:8000", api_key="k")


async def test_connection_failure_is_fatal_after_retry(monkeypatch) -> None:
    monkeypatch.setattr(
        httpx, "AsyncClient", _fake_client(raises=httpx.ConnectError("refused"))
    )
    with pytest.raises(PreflightError, match="unreachable"):
        await EndpointReachability.check(node_kind="ocr", base_url="http://nope:9999")


async def test_base_node_preflight_is_a_noop() -> None:
    # A model-free node inherits the default no-op preflight — it must never raise.
    node = FigureEntryNode(id="entry", config=FigureEntryConfig())
    assert await node.preflight() is None
