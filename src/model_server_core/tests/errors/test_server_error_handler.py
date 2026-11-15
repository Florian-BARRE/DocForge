# ====== Code Summary ======
# Behaviour of ServerErrorHandler through a real app: an unexpected exception is a typed JSON 500 with
# a correlation id, never leaking the exception text, and is logged WITH that same id; HTTPException
# and InvalidInputError keep their own clean answers.

# ====== Third-Party Library Imports ======
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from loggerplusplus.testing import capture

# ====== Internal Project Imports ======
from model_server_core import (
    CORRELATION_ID_HEADER,
    INTERNAL_ERROR_MESSAGE,
    ErrorResponse,
    InvalidInputError,
    ServerErrorHandler,
)

LEAKY_DETAIL = "secret internal detail: /srv/models/weights.bin"


def _client(handler: ServerErrorHandler) -> TestClient:
    app = FastAPI()
    handler.install(app)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError(LEAKY_DETAIL)

    @app.get("/teapot")
    async def teapot() -> None:
        raise HTTPException(status_code=418, detail={"error": "short and stout"})

    @app.get("/invalid")
    async def invalid() -> None:
        raise InvalidInputError("request body is not a decodable image")

    return TestClient(app, raise_server_exceptions=False)


def test_unexpected_exception_is_a_typed_500_with_a_correlation_id() -> None:
    client = _client(ServerErrorHandler(id_factory=lambda: "abc123"))

    response = client.get("/boom")

    assert response.status_code == 500
    body = ErrorResponse.model_validate(response.json())
    assert body.detail.error == INTERNAL_ERROR_MESSAGE
    assert body.detail.correlation_id == "abc123"
    assert response.headers[CORRELATION_ID_HEADER] == "abc123"


def test_the_body_never_leaks_the_exception_or_its_type() -> None:
    response = _client(ServerErrorHandler()).get("/boom")

    assert LEAKY_DETAIL not in response.text
    assert "weights.bin" not in response.text
    assert "RuntimeError" not in response.text
    assert "Traceback" not in response.text


def test_the_full_exception_is_logged_with_the_same_correlation_id() -> None:
    client = _client(ServerErrorHandler(id_factory=lambda: "abc123"))

    with capture(level="ERROR") as logs:
        client.get("/boom")

    assert "correlation_id=abc123" in logs
    assert "RuntimeError" in logs
    assert LEAKY_DETAIL in logs  # full detail belongs in the LOGS, never in the body
    assert "Traceback" in logs
    assert "GET /boom" in logs


def test_each_failure_gets_its_own_generated_correlation_id() -> None:
    client = _client(ServerErrorHandler())

    first = client.get("/boom").json()["detail"]["correlation_id"]
    second = client.get("/boom").json()["detail"]["correlation_id"]

    assert first and second
    assert first != second


def test_http_exception_keeps_its_own_status_and_detail() -> None:
    response = _client(ServerErrorHandler()).get("/teapot")

    assert response.status_code == 418
    assert response.json() == {"detail": {"error": "short and stout"}}


def test_invalid_input_error_is_a_clean_422() -> None:
    with capture(level="WARNING") as logs:
        response = _client(ServerErrorHandler()).get("/invalid")

    assert response.status_code == 422
    assert response.json() == {"detail": {"error": "request body is not a decodable image"}}
    assert "Invalid input" in logs


@pytest.mark.parametrize("path", ["/boom", "/teapot", "/invalid"])
def test_handler_can_be_installed_once_per_app_and_serves_every_path(path: str) -> None:
    assert _client(ServerErrorHandler()).get(path).status_code in {500, 418, 422}
