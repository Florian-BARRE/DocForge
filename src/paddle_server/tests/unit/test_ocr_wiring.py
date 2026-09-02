# ====== Code Summary ======
# Wiring test for POST /ocr — proves the route reaches CONTEXT.paddleocr.read_image() and returns
# its {text, confidence}, that an empty body is rejected (422), and that a lock-wait TimeoutError
# surfaces as HTTP 503 with a Retry-After header. Uses a STUB PaddleOcrService (no paddleocr import),
# so it runs on an AVX-less CPU where PaddlePaddle SIGILLs — this covers the route→service seam that
# neither the normalizer suite (service-free) nor the DocForge node suite (client-side) exercises.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.routers import ocr_router


class _StubOcrService:
    """A no-paddle stand-in for PaddleOcrService — build/unload are no-ops, read_image is canned."""

    def __init__(
        self, *, reading: dict[str, Any] | None = None, raise_timeout: bool = False
    ) -> None:
        self.ready = True
        self._reading = reading or {"text": "FACTURE 1500", "confidence": 0.91}
        self._raise_timeout = raise_timeout

    async def read_image(self, image_bytes: bytes) -> dict[str, Any]:
        """Return the canned reading, or raise TimeoutError to simulate a saturated predict lock."""
        if self._raise_timeout:
            raise TimeoutError("busy")
        return self._reading


def _client() -> TestClient:
    """A TestClient over a bare app with only the OCR router (no lifespan → no real build)."""
    app = FastAPI()
    app.include_router(ocr_router)
    return TestClient(app)


def test_ocr_route_reaches_the_service_and_returns_text_and_confidence() -> None:
    CONTEXT.paddleocr = _StubOcrService()  # type: ignore[assignment]
    response = _client().post("/ocr", content=b"\x89PNG...", headers={"Content-Type": "image/png"})
    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "FACTURE 1500"
    assert body["confidence"] == 0.91


def test_ocr_route_rejects_an_empty_body() -> None:
    CONTEXT.paddleocr = _StubOcrService()  # type: ignore[assignment]
    response = _client().post("/ocr", content=b"")
    assert response.status_code == 422


def test_ocr_route_returns_503_on_lock_timeout() -> None:
    CONTEXT.paddleocr = _StubOcrService(raise_timeout=True)  # type: ignore[assignment]
    response = _client().post("/ocr", content=b"png")
    assert response.status_code == 503
    assert response.headers.get("Retry-After") == "5"
