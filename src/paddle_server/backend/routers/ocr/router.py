# ====== Code Summary ======
# Route definition for POST /ocr — the sidecar's OCR-only contract (see models.py). Raw image bytes
# in, a single joined reading + aggregate confidence out. No request knobs: language and textline
# orientation are pipeline-level (set at build), so the body IS the image. The body is read under the
# core RequestBodyGuard (413 over the cap, 422 when empty) and checked by the core InputValidator (422
# for an undecodable image, through the core InvalidInputError handler); all inference is delegated to
# PaddleOcrService and a lock-wait timeout is translated to HTTP 503. Any other exception is turned
# into the typed 500 by the core ServerErrorHandler: no catch-all here.

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, HTTPException, Request
from loggerplusplus import LoggerClass
from model_server_core import InputValidator, RequestBodyGuard

# ====== Internal Project Imports ======
from libs.paddleocr import PaddleOcrService

# ====== Local Project Imports ======
from .models import OcrResponse

# Seconds a saturated caller is told to wait before retrying (Retry-After of the 503).
RETRY_AFTER_SECONDS = "5"


class OcrRoutes(LoggerClass):
    """
    The POST /ocr route of the Paddle host, bound to its OCR service and the core request guards.

    Per-request tracing goes through this class's logger at DEBUG level — request sizes only, never
    file contents.

    Args:
        service (PaddleOcrService): The OCR-only pipeline service (owns the predict lock).
        body_guard (RequestBodyGuard): Reads the raw body under the `MAX_BODY_BYTES` ceiling.
        input_validator (InputValidator): Checks the body decodes as an image before any inference.
    """

    # Public attributes
    router: APIRouter

    def __init__(
        self,
        service: PaddleOcrService,
        body_guard: RequestBodyGuard,
        input_validator: InputValidator,
    ) -> None:
        LoggerClass.__init__(self)
        self._service = service
        self._body_guard = body_guard
        self._input_validator = input_validator
        self.router = APIRouter()
        self.router.add_api_route("/ocr", self.ocr, methods=["POST"], response_model=OcrResponse)

    async def ocr(self, request: Request) -> OcrResponse:
        # NOTE: the docstring below is published as the OpenAPI description of POST /ocr, which is
        # pinned byte-identical by the characterization golden: keep it free of implementation notes.
        """
        OCR a single image with PaddleOCR (text detection + recognition) — the OCR-only capability,
        distinct from POST /layout-parsing (full layout). No base64 wrapping: the body IS the image.

        Args:
            request (Request): Raw request — the body IS the image bytes (Content-Type: image/png).

        Returns:
            OcrResponse: `{text, confidence}` — see models.py.
        """
        # 1. Read the raw body under the hard size cap — no pydantic model, the request IS the image.
        #    An oversized upload is refused 413 (before/while buffering) instead of OOMing the
        #    container; an empty one is 422.
        image_bytes = await self._body_guard.read_non_empty(request)
        self.logger.debug(f"POST /ocr: {len(image_bytes)} bytes")

        # 2. Reject an undecodable image as a client error BEFORE taking the lock or spending inference.
        self._input_validator.verify_image(image_bytes)

        # 3. Delegate to the OCR service; a lock-wait timeout means the service is saturated -> 503
        #    with Retry-After. Any other failure is a genuine server fault (typed 500 from the core).
        try:
            result = await self._service.read_image(image_bytes)
        except TimeoutError:
            raise HTTPException(
                status_code=503,
                detail={"error": "server overloaded — try again shortly"},
                headers={"Retry-After": RETRY_AFTER_SECONDS},
            )

        return OcrResponse(**result)
