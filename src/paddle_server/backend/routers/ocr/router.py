# ====== Code Summary ======
# Route definition for POST /ocr — the sidecar's OCR-only contract (see models.py). Raw image bytes
# in, a single joined reading + aggregate confidence out. No request knobs: language and textline
# orientation are pipeline-level (set at build), so the body IS the image. All inference is delegated
# to CONTEXT.paddleocr; a lock-wait timeout is translated to HTTP 503.

# ====== Standard Library Imports ======

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, HTTPException, Request
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.utils.error_handling import auto_handle_errors
from backend.libs.utils.request_limits import RequestBodyGuard

# ====== Local Project Imports ======
from .models import OcrResponse

router = APIRouter()

# Module-level logger for per-request tracing — request sizes/timings only, never file contents.
logger = loggerplusplus.bind(identifier="OcrRouter")


@router.post("/ocr", response_model=OcrResponse)
@auto_handle_errors
async def ocr(request: Request) -> OcrResponse:
    """
    OCR a single image with PaddleOCR (text detection + recognition) — the OCR-only capability,
    distinct from POST /layout-parsing (full layout). No base64 wrapping: the body IS the image.

    Args:
        request (Request): Raw request — the body IS the image bytes (Content-Type: image/png).

    Returns:
        OcrResponse: `{text, confidence}` — see models.py.
    """
    # 1. Read the raw body under a hard size cap — no pydantic model, the request IS the image.
    #    An oversized upload is refused 413 (before/while buffering) instead of OOMing the container.
    image_bytes = await RequestBodyGuard.read_capped(request, CONTEXT.CONFIG.PADDLE_MAX_BODY_BYTES)
    logger.debug(f"POST /ocr: {len(image_bytes)} bytes")

    if not image_bytes:
        raise HTTPException(status_code=422, detail={"error": "empty request body"})

    # 2. Delegate to the OCR service; a lock-wait timeout means the service is saturated.
    try:
        result = await CONTEXT.paddleocr.read_image(image_bytes)
    except TimeoutError:
        raise HTTPException(
            status_code=503,
            detail={"error": "server overloaded — try again shortly"},
            headers={"Retry-After": "5"},
        )

    return OcrResponse(**result)
