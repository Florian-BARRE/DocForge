# ====== Code Summary ======
# Wiring test for POST /layout-parsing — proves LayoutParsingRoutes reaches the PpStructureService parse_pdf() and returns its
# result, and maps its expected failures to the right HTTP status: an empty body -> 422, an undecodable
# PDF (client error, caught by the core InputValidator before the service) -> 422 with a clean
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
from backend.routers import LayoutParsingRoutes
from tests.support.paddle_app import MAX_BODY_BYTES, VALID_PDF, SmallLimitsConfig

RESULT: dict[str, Any] = {
    "pages": [],
    "n_pages": 0,
    "engine": {"paddleocr": "3.7.0", "pipeline": "PP-StructureV3", "sub_pipelines": {}},
}


@pytest.fixture
def service() -> MagicMock:
    stub = MagicMock()
    stub.parse_pdf = AsyncMock(return_value=RESULT)
    return stub


@pytest.fixture
def client(service: MagicMock) -> TestClient:
    """The route alone, wired like PaddleServer does, with the core handlers installed."""
    app = FastAPI()
    ServerErrorHandler().install(app)
    routes = LayoutParsingRoutes(
        service,
        RequestBodyGuard(max_bytes=MAX_BODY_BYTES),
        InputValidator.from_config(SmallLimitsConfig),
    )
    app.include_router(routes.router)
    return TestClient(app, raise_server_exceptions=False)


def test_layout_route_reaches_the_service_and_returns_its_result(
    client: TestClient, service: MagicMock
) -> None:
    response = client.post(
        "/layout-parsing", content=VALID_PDF, headers={"Content-Type": "application/pdf"}
    )
    assert response.status_code == 200
    assert response.json() == RESULT
    service.parse_pdf.assert_awaited_once()
    assert service.parse_pdf.await_args.args[0] == VALID_PDF


def test_layout_route_rejects_an_empty_body(client: TestClient, service: MagicMock) -> None:
    response = client.post("/layout-parsing", content=b"")
    assert response.status_code == 422
    assert response.json() == {"detail": {"error": "empty request body"}}
    service.parse_pdf.assert_not_awaited()


def test_layout_route_returns_503_on_lock_timeout(client: TestClient, service: MagicMock) -> None:
    service.parse_pdf.side_effect = TimeoutError("busy")
    response = client.post("/layout-parsing", content=VALID_PDF)
    assert response.status_code == 503
    assert response.headers.get("Retry-After") == "5"
    assert response.json() == {"detail": {"error": "server overloaded — try again shortly"}}


def test_layout_route_returns_422_on_undecodable_pdf(
    client: TestClient, service: MagicMock
) -> None:
    # A malformed upload is a client error: the core validator raises InvalidInputError before the
    # service and the core handler maps it to 422 with a clean message — NOT a 500.
    response = client.post("/layout-parsing", content=b"not-a-pdf")
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "request body is not a decodable PDF"
    service.parse_pdf.assert_not_awaited()
