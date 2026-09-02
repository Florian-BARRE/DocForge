"""The PaddleOCR provider brick — the OCR-family node backed by the paddle_server sidecar's
OCR-only endpoint (_read over a mocked httpx, preflight, registration, config defaults).

Everything is offline: the node's httpx client is monkeypatched, so no live paddle_server is
needed. Mirrors how the pp_structure/mistral bricks are tested (no real engine).
"""

import asyncio

import httpx
import pytest

from shared_libs.pipelines.nodes.ocr.base import OcrConsumes
from shared_libs.pipelines.nodes.ocr.paddle.config import OcrPaddleConfig
from shared_libs.pipelines.nodes.ocr.paddle.core import OcrPaddleNode
from shared_libs.pipelines.nodes.openai_compat.preflight import PreflightError
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import FigureItem

# ==================== registration + config ====================


def test_paddle_is_registered_under_the_ocr_family() -> None:
    """The node self-registers as ('ocr', 'paddle') and surfaces in the palette."""
    assert "paddle" in NodeRegistry.kinds("ocr")
    assert NodeRegistry.get("ocr", "paddle") is OcrPaddleNode


def test_config_defaults_base_url_to_the_in_stack_sidecar() -> None:
    """base_url defaults to the sidecar so the provider is reachable out of the box, no key needed."""
    config = OcrPaddleConfig()
    assert config.base_url == "http://paddle_server:80"
    assert config.api_key == ""


def test_config_strips_pasted_whitespace_on_base_url() -> None:
    """A trailing newline pasted into the endpoint is stripped before it breaks the request line."""
    config = OcrPaddleConfig(base_url="  http://paddle_server:80\n")
    assert config.base_url == "http://paddle_server:80"


# ==================== node — _read over a mocked httpx client ====================


class _FakeResponse:
    """A stand-in httpx.Response carrying a canned JSON body."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def _fake_async_client(*, captured: dict, payload: dict):
    """An httpx.AsyncClient stand-in whose .post() records the call and returns a canned response."""

    class _Client:
        def __init__(self, *args: object, **kwargs: object) -> None:
            captured["init"] = kwargs

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

        async def post(
            self,
            url: str,
            content: bytes | None = None,
            headers: dict | None = None,
        ) -> _FakeResponse:
            captured["url"] = url
            captured["content"] = content
            captured["headers"] = headers
            return _FakeResponse(payload)

    return _Client


def test_read_posts_raw_bytes_and_returns_text_and_confidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_read POSTs the raw image bytes with the content-type + bearer and reads {text, confidence}."""
    captured: dict = {}
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        _fake_async_client(captured=captured, payload={"text": "FACTURE 1500", "confidence": 0.91}),
    )
    node = OcrPaddleNode(
        id="o", config=OcrPaddleConfig(base_url="http://paddle_server:80", api_key="tok")
    )
    figure = FigureItem(block_id="f1", image=b"\x89PNG...")
    result = asyncio.run(node.run(OcrConsumes(figure=figure)))

    # 1. The raw image bytes go in the body with the content-type + bearer.
    assert captured["url"] == "/ocr"
    assert captured["content"] == b"\x89PNG..."
    assert captured["headers"]["Content-Type"] == "image/png"
    assert captured["headers"]["Authorization"] == "Bearer tok"

    # 2. The mocked response maps into the figure's read_text + the confidence score.
    assert result.figure.read_text == "FACTURE 1500"
    assert result.score == 0.91
    assert figure.read_text == ""  # the input item was NOT mutated (copy relay)


def test_read_omits_the_bearer_when_no_key_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """An in-stack sidecar needs no auth — no Authorization header is sent when api_key is empty."""
    captured: dict = {}
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        _fake_async_client(captured=captured, payload={"text": "x", "confidence": 0.5}),
    )
    node = OcrPaddleNode(id="o", config=OcrPaddleConfig())
    asyncio.run(node.run(OcrConsumes(figure=FigureItem(block_id="f1", image=b"png"))))
    assert "Authorization" not in captured["headers"]


def test_read_defaults_confidence_to_zero_on_a_missing_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed sidecar body (no confidence) degrades to score 0.0 rather than crashing."""
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        _fake_async_client(captured={}, payload={"text": "only text"}),
    )
    node = OcrPaddleNode(id="o", config=OcrPaddleConfig())
    result = asyncio.run(node.run(OcrConsumes(figure=FigureItem(block_id="f1", image=b"png"))))
    assert result.figure.read_text == "only text"
    assert result.score == 0.0


# ==================== node — preflight ====================


class _ProbeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def _preflight_client(*, status_code: int):
    """An httpx.AsyncClient stand-in for EndpointReachability's GET probe."""

    class _Client:
        def __init__(self, *args: object, **kwargs: object) -> None: ...

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *exc: object) -> None: ...

        async def get(self, url: str, headers: dict | None = None) -> _ProbeResponse:
            return _ProbeResponse(status_code)

    return _Client


def test_preflight_passes_when_health_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any answer on /health (even non-200) proves the sidecar is up — preflight passes."""
    monkeypatch.setattr(httpx, "AsyncClient", _preflight_client(status_code=200))
    node = OcrPaddleNode(id="o", config=OcrPaddleConfig())
    assert asyncio.run(node.preflight()) is None


def test_preflight_fails_on_rejected_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 401 on /health surfaces a rejected bearer token before any spend."""
    monkeypatch.setattr(httpx, "AsyncClient", _preflight_client(status_code=401))
    node = OcrPaddleNode(id="o", config=OcrPaddleConfig(api_key="bad"))
    with pytest.raises(PreflightError):
        asyncio.run(node.preflight())
