# ====== Code Summary ======
# Route definition for POST /vl-parse — the PaddleOCR-VL 1.6 sidecar endpoint. Raw PDF bytes in, the
# SAME clean reading-ordered per-page block contract /layout-parsing returns out (it reuses that
# route's LayoutParsingResponse model on purpose — an identical wire shape means the DocForge IR
# mapper is shared). The pipeline is built LAZILY inside CONTEXT.paddleocr_vl.parse_pdf on the first
# request, so this route pays the model download/load once (surfaced as a slow first response), never
# at startup. Sub-pipeline toggles are optional query params overriding the pipeline defaults; a
# lock-wait timeout is translated to HTTP 503.

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, HTTPException, Request
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.utils.error_handling import auto_handle_errors
from backend.libs.utils.request_limits import RequestBodyGuard
from libs.validation import InvalidInputError

# ====== Local Project Imports ======
from ..layout_parsing.models import LayoutParsingResponse

router = APIRouter()

# Module-level logger for per-request tracing — request sizes/timings only, never file contents.
logger = loggerplusplus.bind(identifier="VlParsingRouter")


@router.post("/vl-parse", response_model=LayoutParsingResponse)
@auto_handle_errors
async def vl_parse(
    request: Request,
    use_chart_recognition: bool | None = None,
    use_seal_recognition: bool | None = None,
    use_ocr_for_image_block: bool | None = None,
) -> LayoutParsingResponse:
    """
    Parse a PDF's layout with PaddleOCR-VL 1.6 — same contract shape as /layout-parsing (no base64
    wrapping, explicit per-page pixel dims, tables as HTML, formulas as LaTeX already inlined).

    The pipeline is built on demand: the FIRST request downloads + loads the PP-DocLayoutV3 and
    PaddleOCR-VL-1.6-0.9B models (minutes on a cold cache), so it can be slow; subsequent requests
    reuse the warm pipeline.

    Args:
        request (Request): Raw request — the body IS the PDF bytes (Content-Type: application/pdf).
        use_chart_recognition (bool | None): Per-request override of the pipeline default (OFF).
        use_seal_recognition (bool | None): Per-request override of the pipeline default (OFF).
        use_ocr_for_image_block (bool | None): Per-request override of the pipeline default (OFF).

    Returns:
        LayoutParsingResponse: `{pages, n_pages, engine}` — the shared sidecar contract.
    """
    # 1. Read the raw body under a hard size cap — the request IS the PDF. An oversized upload is
    #    refused 413 (before/while buffering) instead of OOMing the container.
    pdf_bytes = await RequestBodyGuard.read_capped(request, CONTEXT.CONFIG.PADDLE_MAX_BODY_BYTES)
    logger.debug(f"POST /vl-parse: {len(pdf_bytes)} bytes")

    if not pdf_bytes:
        raise HTTPException(status_code=422, detail={"error": "empty request body"})

    # 2. Delegate to the lazy pipeline service; classify its two expected failures distinctly from a
    #    genuine server fault (which @auto_handle_errors still turns into a non-leaky 500):
    #      - an undecodable PDF is a CLIENT error -> 422 with a clean message;
    #      - a lock-wait timeout means the service is saturated -> 503 with Retry-After.
    try:
        result = await CONTEXT.paddleocr_vl.parse_pdf(
            pdf_bytes,
            use_chart_recognition=use_chart_recognition,
            use_seal_recognition=use_seal_recognition,
            use_ocr_for_image_block=use_ocr_for_image_block,
        )
    except InvalidInputError as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc)})
    except TimeoutError:
        raise HTTPException(
            status_code=503,
            detail={"error": "server overloaded — try again shortly"},
            headers={"Retry-After": "5"},
        )

    return LayoutParsingResponse(**result)
