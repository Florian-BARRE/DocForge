# ====== Code Summary ======
# An httpx.AsyncClient stand-in for the parser nodes' sidecar call: ``post`` records the request (route,
# raw body, headers, query params) and answers a canned JSON body. ``install`` patches httpx.AsyncClient
# AND empties the process-wide HttpClientPool for the test, so a client cached by another test (the pool
# keys by base URL) can never answer instead of this fake, nor this fake outlive the test.

# ====== Third-Party Library Imports ======
import httpx
import pytest

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.http_pool import HttpClientPool


class _CannedResponse:
    """A stand-in httpx.Response carrying a canned JSON body."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeSidecar:
    """Records the one request a parser node sends and answers a canned payload."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.request: dict = {}

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Route every httpx.AsyncClient of the test to this fake, behind an empty client pool."""
        sidecar = self

        class _Client:
            def __init__(self, *args: object, **kwargs: object) -> None:
                self.is_closed = False

            async def __aenter__(self) -> "_Client":
                return self

            async def __aexit__(self, *exc: object) -> None:
                return None

            async def post(
                self,
                url: str,
                content: bytes | None = None,
                params: dict | None = None,
                headers: dict | None = None,
            ) -> _CannedResponse:
                sidecar.request = {
                    "url": url,
                    "content": content.decode("latin-1") if content is not None else None,
                    "params": params,
                    "headers": headers,
                }
                return _CannedResponse(sidecar._payload)

        monkeypatch.setattr(httpx, "AsyncClient", _Client)
        monkeypatch.setattr(HttpClientPool, "_clients", {})
