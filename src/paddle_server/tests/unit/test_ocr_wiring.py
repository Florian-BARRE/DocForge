# ====== Code Summary ======
# Wiring test for POST /ocr — proves OcrRoutes reaches the PaddleOcrService read_image() and returns its
# result, and maps its expected failures to the right HTTP status: an empty body -> 422, an undecodable
# image (client error, caught by the core InputValidator before the service) -> 422 with a clean
# message (not a 500 leaking a raw PaddleX exception), and a lock-wait TimeoutError -> 503 with
# Retry-After. Uses a STUB service (no paddle import), so it runs on an AVX-less CPU where PaddlePaddle
# SIGILLs. The 413 guard and the typed 500 are covered for the three routes in test_route_guards.py.

# ====== Standard Library Imports ======
from typing import Any
from unittest.mock import AsyncMock, MagicMock

# ====== Third-Party Library Imports ======
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from model_server_core import InputValidator, RequestBodyGuard, ServerErrorHandler

# ====== Internal Project Imports ======
from backend.routers import OcrRoutes
from tests.support.paddle_app import MAX_BODY_BYTES, SmallLimitsConfig, valid_png_bytes

RESULT: dict[str, Any] = {"text": "FACTURE 1500", "confidence": 0.91}


@pytest.fixture
def service() -> MagicMock:
    stub = MagicMock()
    stub.read_image = AsyncMock(return_value=RESULT)
    return stub


@pytest.fixture
def client(service: MagicMock) -> TestClient:
    """The route alone, wired like PaddleServer does, with the core handlers installed."""
    app = FastAPI()
    ServerErrorHandler().install(app)
    routes = OcrRoutes(
        service,
        RequestBodyGuard(max_bytes=MAX_BODY_BYTES),
        InputValidator.from_config(SmallLimitsConfig),
    )
    app.include_router(routes.router)
    return TestClient(app, raise_server_exceptions=False)


def test_ocr_route_reaches_the_service_and_returns_its_result(
    client: TestClient, service: MagicMock
) -> None:
    response = client.post("/ocr", content=valid_png_bytes(), headers={"Content-Type": "image/png"})
    assert response.status_code == 200
    assert response.json() == RESULT
    service.read_image.assert_awaited_once()
    assert service.read_image.await_args.args[0] == valid_png_bytes()


def test_ocr_route_rejects_an_empty_body(client: TestClient, service: MagicMock) -> None:
    response = client.post("/ocr", content=b"")
    assert response.status_code == 422
    assert response.json() == {"detail": {"error": "empty request body"}}
    service.read_image.assert_not_awaited()


def test_ocr_route_returns_503_on_lock_timeout(client: TestClient, service: MagicMock) -> None:
    service.read_image.side_effect = TimeoutError("busy")
    response = client.post("/ocr", content=valid_png_bytes())
    assert response.status_code == 503
    assert response.headers.get("Retry-After") == "5"
    assert response.json() == {"detail": {"error": "server overloaded — try again shortly"}}


def test_ocr_route_returns_422_on_undecodable_image(client: TestClient, service: MagicMock) -> None:
    # A malformed upload is a client error: the core validator raises InvalidInputError before the
    # service and the core handler maps it to 422 with a clean message — NOT a 500.
    response = client.post("/ocr", content=b"not-a-image")
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "request body is not a decodable image"
    service.read_image.assert_not_awaited()
