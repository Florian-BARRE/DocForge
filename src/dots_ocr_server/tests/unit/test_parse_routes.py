# ====== Code Summary ======
# Unit tests for the POST /parse guards of ParseRoutes, over a STUB parse service (no engine, no lock,
# no normalizer): the raw-body ceiling (413, declared and streamed), the empty body (422), the
# undecodable PDFs (422 through the core InvalidInputError handler), the lock-wait
# timeout (503 + Retry-After) and the typed 500. The guards were untested before R-27 (S-19 only
# pinned them end to end); the rejects must never reach the service. Torch-free and GPU-free.

# ====== Standard Library Imports ======
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

# ====== Third-Party Library Imports ======
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from model_server_core import (
    CORRELATION_ID_HEADER,
    INTERNAL_ERROR_MESSAGE,
    InputValidator,
    RequestBodyGuard,
    ServerErrorHandler,
)

# ====== Internal Project Imports ======
from backend.routers import ParseRoutes
from tests.support.dots_ocr_app import MAX_BODY_BYTES, VALID_PDF, SmallLimitsConfig

RESULT: dict[str, Any] = {
    "pages": [],
    "n_pages": 0,
    "engine": {"dots_ocr": "test", "model": "rednote-hilab/dots.ocr", "backend": "transformers"},
}


@pytest.fixture
def service() -> MagicMock:
    stub = MagicMock()
    stub.parse_pdf = AsyncMock(return_value=RESULT)
    return stub


@pytest.fixture
def client(service: MagicMock) -> TestClient:
    """The /parse route alone, wired like DotsOcrServer does, with the core handlers installed."""
    app = FastAPI()
    ServerErrorHandler().install(app)
    routes = ParseRoutes(
        service,
        RequestBodyGuard(max_bytes=MAX_BODY_BYTES),
        InputValidator.from_config(SmallLimitsConfig),
    )
    app.include_router(routes.router)
    return TestClient(app, raise_server_exceptions=False)


def test_a_valid_pdf_reaches_the_service_and_returns_its_result(
    client: TestClient, service: MagicMock
) -> None:
    response = client.post("/parse", content=VALID_PDF)

    assert response.status_code == 200
    assert response.json() == RESULT
    service.parse_pdf.assert_awaited_once_with(VALID_PDF)


def test_declared_content_length_over_the_cap_is_413(
    client: TestClient, service: MagicMock
) -> None:
    response = client.post("/parse", content=b"x" * (MAX_BODY_BYTES + 1))

    assert response.status_code == 413
    assert response.json() == {
        "detail": {"error": f"request body exceeds the {MAX_BODY_BYTES}-byte limit"}
    }
    service.parse_pdf.assert_not_awaited()


def test_streamed_body_over_the_cap_without_content_length_is_413(
    client: TestClient, service: MagicMock
) -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(MAX_BODY_BYTES // 256 + 2):
            yield b"x" * 256

    response = client.post("/parse", content=chunks())

    assert response.status_code == 413
    service.parse_pdf.assert_not_awaited()


def test_empty_body_is_422(client: TestClient, service: MagicMock) -> None:
    response = client.post("/parse", content=b"")

    assert response.status_code == 422
    assert response.json() == {"detail": {"error": "empty request body"}}
    service.parse_pdf.assert_not_awaited()


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (b"%PDF but truncated garbage", "request body is not a decodable PDF"),
        (b"\x89PNG\r\n\x1a\n not a pdf", "request body is not a decodable PDF"),
    ],
)
def test_an_undecodable_pdf_is_422_and_never_reaches_the_service(
    client: TestClient, service: MagicMock, body: bytes, message: str
) -> None:
    response = client.post("/parse", content=body)

    assert response.status_code == 422
    assert response.json() == {"detail": {"error": message}}
    service.parse_pdf.assert_not_awaited()


def test_lock_wait_timeout_is_503_with_retry_after(client: TestClient, service: MagicMock) -> None:
    service.parse_pdf.side_effect = TimeoutError("busy")

    response = client.post("/parse", content=VALID_PDF)

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    assert response.json() == {"detail": {"error": "server overloaded — try again shortly"}}


def test_unexpected_failure_is_a_typed_500_with_a_correlation_id(
    client: TestClient, service: MagicMock
) -> None:
    service.parse_pdf.side_effect = RuntimeError("secret internal detail")

    response = client.post("/parse", content=VALID_PDF)

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["error"] == INTERNAL_ERROR_MESSAGE
    assert detail["correlation_id"] == response.headers[CORRELATION_ID_HEADER]
    assert "secret internal detail" not in response.text
