# ====== Code Summary ======
# Route definition for POST /parse — the dots.ocr sidecar endpoint. Raw PDF bytes in, the shared
# reading-ordered per-page block contract out (the SAME shape mineru_server's /parse returns, so the
# DocForge IR mapper family is shared). The dots.ocr VLM model is loaded LAZILY inside
# CONTEXT.dots_ocr.parse_pdf on the first request, so this route pays the model download/load once (a
# slow first response), never at startup. A lock-wait timeout is translated to HTTP 503; an undecodable
# PDF to HTTP 422.

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, HTTPException, Request
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.utils.error_handling import auto_handle_errors
from backend.libs.utils.request_limits import RequestBodyGuard
from libs.validation import InvalidInputError

# ====== Local Project Imports ======
from .models import ParseResponse

router = APIRouter()

# Module-level logger for per-request tracing — request sizes/timings only, never file contents.
logger = loggerplusplus.bind(identifier="ParseRouter")


@router.post("/parse", response_model=ParseResponse)
@auto_handle_errors
async def parse(request: Request) -> ParseResponse:
    """
    Parse a PDF's layout with dots.ocr — the shared sidecar contract (no base64 wrapping, explicit
    per-page rendered pixel dims, tables as HTML, formulas as LaTeX already inlined).

    The model is built on demand: the FIRST request downloads + loads the dots.ocr weights on CUDA
    (minutes on a cold cache), so it can be slow; subsequent requests reuse the warm model.

    Args:
        request (Request): Raw request — the body IS the PDF bytes (Content-Type: application/pdf).

    Returns:
        ParseResponse: `{pages, n_pages, engine}` — the shared sidecar contract.
    """
    # 1. Read the raw body under a hard size cap — the request IS the PDF. An oversized upload is
    #    refused 413 (before/while buffering) instead of OOMing the container.
    pdf_bytes = await RequestBodyGuard.read_capped(request, CONTEXT.CONFIG.DOTS_OCR_MAX_BODY_BYTES)
    logger.debug(f"POST /parse: {len(pdf_bytes)} bytes")

    if not pdf_bytes:
        raise HTTPException(status_code=422, detail={"error": "empty request body"})

    # 2. Delegate to the parse service; classify its two expected failures distinctly from a genuine
    #    server fault (which @auto_handle_errors still turns into a non-leaky 500):
    #      - an undecodable PDF is a CLIENT error -> 422 with a clean message;
    #      - a lock-wait timeout means the service is saturated -> 503 with Retry-After.
    try:
        result = await CONTEXT.dots_ocr.parse_pdf(pdf_bytes)
    except InvalidInputError as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc)})
    except TimeoutError:
        raise HTTPException(
            status_code=503,
            detail={"error": "server overloaded — try again shortly"},
            headers={"Retry-After": "5"},
        )

    return ParseResponse(**result)
