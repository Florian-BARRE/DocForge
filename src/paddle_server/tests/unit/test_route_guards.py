# ====== Code Summary ======
# Unit tests for the guards the three raw-body routes share (/ocr, /layout-parsing, /vl-parse), over a
# STUB service: the declared and streamed 413 of the core RequestBodyGuard, and the typed 500 of the
# core ServerErrorHandler (a generic body plus a correlation id, never str(exc)). The same cases run on
# each route, since they must stay symmetric; a rejected request must never reach the service.
# Paddle-free: no pipeline is built.

# ====== Standard Library Imports ======
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

# ====== Third-Party Library Imports ======
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from model_server_core import (
    CORRELATION_ID_HEADER,
    INTERNAL_ERROR_MESSAGE,
    InputValidator,
    RequestBodyGuard,
    ServerErrorHandler,
)

# ====== Internal Project Imports ======
from backend.routers import LayoutParsingRoutes, OcrRoutes, VlParsingRoutes
from tests.support.paddle_app import (
    MAX_BODY_BYTES,
    VALID_PDF,
    SmallLimitsConfig,
    valid_png_bytes,
)


@dataclass(frozen=True)
class RouteCase:
    """One raw-body route: its class, URL, service method and a valid body."""

    path: str
    routes: Callable[..., Any]
    method: str
    valid_body: bytes


CASES = {
    "ocr": RouteCase("/ocr", OcrRoutes, "read_image", valid_png_bytes()),
    "layout": RouteCase("/layout-parsing", LayoutParsingRoutes, "parse_pdf", VALID_PDF),
    "vl": RouteCase("/vl-parse", VlParsingRoutes, "parse_pdf", VALID_PDF),
}


@pytest.fixture(params=list(CASES))
def case(request: pytest.FixtureRequest) -> RouteCase:
    return CASES[request.param]


@pytest.fixture
def service(case: RouteCase) -> MagicMock:
    stub = MagicMock()
    setattr(stub, case.method, AsyncMock(return_value={}))
    return stub


@pytest.fixture
def client(case: RouteCase, service: MagicMock) -> TestClient:
    """The route alone, wired like PaddleServer does, with the core handlers installed."""
    app = FastAPI()
    ServerErrorHandler().install(app)
    router: APIRouter = case.routes(
        service,
        RequestBodyGuard(max_bytes=MAX_BODY_BYTES),
        InputValidator.from_config(SmallLimitsConfig),
    ).router
    app.include_router(router)
    # raise_server_exceptions=False: the typed 500 is an HTTP answer the tests assert on, not an
    # exception to re-raise into the test client.
    return TestClient(app, raise_server_exceptions=False)


def test_declared_content_length_over_the_cap_is_413(
    client: TestClient, service: MagicMock, case: RouteCase
) -> None:
    response = client.post(case.path, content=b"x" * (MAX_BODY_BYTES + 1))

    assert response.status_code == 413
    assert response.json() == {
        "detail": {"error": f"request body exceeds the {MAX_BODY_BYTES}-byte limit"}
    }
    getattr(service, case.method).assert_not_awaited()


def test_streamed_body_over_the_cap_without_content_length_is_413(
    client: TestClient, service: MagicMock, case: RouteCase
) -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(MAX_BODY_BYTES // 256 + 2):
            yield b"x" * 256

    response = client.post(case.path, content=chunks())

    assert response.status_code == 413
    getattr(service, case.method).assert_not_awaited()


def test_body_exactly_at_the_cap_passes_the_guard(
    client: TestClient, service: MagicMock, case: RouteCase
) -> None:
    # Not a decodable body, so it is refused by the validator (422): the guard let it through.
    response = client.post(case.path, content=b"x" * MAX_BODY_BYTES)

    assert response.status_code == 422
    getattr(service, case.method).assert_not_awaited()


def test_unexpected_failure_is_a_typed_500_with_a_correlation_id(
    client: TestClient, service: MagicMock, case: RouteCase
) -> None:
    """R-27 (approved behaviour change): the 500 body is a generic typed error plus a correlation id,
    never `str(exc)` (was `{"detail": {"error": "<exception text>"}}`)."""
    getattr(service, case.method).side_effect = RuntimeError("secret internal detail")

    response = client.post(case.path, content=case.valid_body)

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["error"] == INTERNAL_ERROR_MESSAGE
    assert detail["correlation_id"] == response.headers[CORRELATION_ID_HEADER]
    assert "secret internal detail" not in response.text
