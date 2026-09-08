# ====== Code Summary ======
# Wiring test for POST /vl-parse — proves the route reaches CONTEXT.paddleocr_vl.parse_pdf() and maps
# its expected failures to the right HTTP status: an undecodable PDF (client error) -> 422 with a
# clean message (not a 500 leaking a raw PaddleX exception), and a lock-wait TimeoutError -> 503 with
# Retry-After. Uses a STUB PaddleOcrVlService (no paddle import), so it runs on an AVX-less CPU where
# PaddlePaddle SIGILLs.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.routers import vl_parsing_router


class _StubPaddleOcrVlService:
    """A no-paddle stand-in for PaddleOcrVlService — parse_pdf is canned or raises on demand."""

    def __init__(self, *, raise_timeout: bool = False, raise_invalid: bool = False) -> None:
        self.ready = False  # lazily built — starts not-ready, mirrors the real service
        self._raise_timeout = raise_timeout
        self._raise_invalid = raise_invalid

    async def parse_pdf(self, pdf_bytes: bytes, **_: Any) -> dict[str, Any]:
        """Return a canned result, or raise to simulate a bad PDF / a saturated predict lock."""
        if self._raise_invalid:
            from libs.validation import InvalidInputError  # noqa: PLC0415

            raise InvalidInputError("request body is not a decodable PDF")
        if self._raise_timeout:
            raise TimeoutError("busy")
        return {
            "pages": [],
            "n_pages": 0,
            "engine": {
                "paddleocr": "3.7.0",
                "pipeline": "PaddleOCR-VL-v1.6",
                "sub_pipelines": {},
            },
        }


def _client() -> TestClient:
    """A TestClient over a bare app with only the vl-parsing router (no lifespan → no build)."""
    from config_loader import PaddleServerConfig  # noqa: PLC0415

    CONTEXT.CONFIG = PaddleServerConfig  # type: ignore[assignment]
    app = FastAPI()
    app.include_router(vl_parsing_router)
    return TestClient(app)


def test_vl_route_reaches_the_service_and_returns_pages() -> None:
    CONTEXT.paddleocr_vl = _StubPaddleOcrVlService()  # type: ignore[assignment]
    response = _client().post(
        "/vl-parse", content=b"%PDF-1.4 ...", headers={"Content-Type": "application/pdf"}
    )
    assert response.status_code == 200
    assert response.json()["n_pages"] == 0


def test_vl_route_rejects_an_empty_body() -> None:
    CONTEXT.paddleocr_vl = _StubPaddleOcrVlService()  # type: ignore[assignment]
    response = _client().post("/vl-parse", content=b"")
    assert response.status_code == 422


def test_vl_route_returns_503_on_lock_timeout() -> None:
    CONTEXT.paddleocr_vl = _StubPaddleOcrVlService(raise_timeout=True)  # type: ignore[assignment]
    response = _client().post("/vl-parse", content=b"%PDF")
    assert response.status_code == 503
    assert response.headers.get("Retry-After") == "5"


def test_vl_route_returns_422_on_undecodable_pdf() -> None:
    CONTEXT.paddleocr_vl = _StubPaddleOcrVlService(raise_invalid=True)  # type: ignore[assignment]
    response = _client().post("/vl-parse", content=b"not-a-pdf")
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "request body is not a decodable PDF"
