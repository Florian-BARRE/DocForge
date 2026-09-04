# ====== Code Summary ======
# Route definition for POST /layout-parsing — the sidecar's OWN contract (see models.py). Raw PDF
# bytes in, a clean reading-ordered per-page block list out. Sub-pipeline toggles are optional
# query params that override the pipeline-level defaults for this one request; `use_doc_unwarping`
# is intentionally NOT exposed here (always False — see libs/ppstructure/service.py). All inference
# is delegated to CONTEXT.ppstructure; a lock-wait timeout is translated to HTTP 503.

# ====== Standard Library Imports ======

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, HTTPException, Request
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.utils.error_handling import auto_handle_errors
from backend.libs.utils.request_limits import RequestBodyGuard

# ====== Local Project Imports ======
from .models import LayoutParsingResponse

router = APIRouter()

# Module-level logger for per-request tracing — request sizes/timings only, never file contents.
logger = loggerplusplus.bind(identifier="LayoutParsingRouter")


@router.post("/layout-parsing", response_model=LayoutParsingResponse)
@auto_handle_errors
async def layout_parsing(
    request: Request,
    use_table_recognition: bool | None = None,
    use_formula_recognition: bool | None = None,
    use_seal_recognition: bool | None = None,
    use_doc_orientation_classify: bool | None = None,
) -> LayoutParsingResponse:
    """
    Parse a PDF's layout with PP-StructureV3 -- our own contract, not PaddleX's `paddlex --serve`
    shape (see the research plan §B.4): no base64 wrapping, explicit per-page pixel dims, no
    heavy `outputImages`/`inputImage` on the wire.

    Args:
        request (Request): Raw request — the body IS the PDF bytes (Content-Type: application/pdf).
        use_table_recognition (bool | None): Per-request override of the pipeline default.
        use_formula_recognition (bool | None): Per-request override of the pipeline default.
        use_seal_recognition (bool | None): Per-request override of the pipeline default.
        use_doc_orientation_classify (bool | None): Per-request override of the pipeline default.

    Returns:
        LayoutParsingResponse: `{pages, n_pages, engine}` — see models.py.
    """
    # 1. Read the raw body under a hard size cap — no pydantic model, the request IS the PDF. An
    #    oversized upload is refused 413 (before/while buffering) instead of OOMing the container.
    pdf_bytes = await RequestBodyGuard.read_capped(request, CONTEXT.CONFIG.PADDLE_MAX_BODY_BYTES)
    logger.debug(f"POST /layout-parsing: {len(pdf_bytes)} bytes")

    if not pdf_bytes:
        raise HTTPException(status_code=422, detail={"error": "empty request body"})

    # 2. Delegate to the pipeline service; a lock-wait timeout means the service is saturated.
    try:
        result = await CONTEXT.ppstructure.parse_pdf(
            pdf_bytes,
            use_table_recognition=use_table_recognition,
            use_formula_recognition=use_formula_recognition,
            use_seal_recognition=use_seal_recognition,
            use_doc_orientation_classify=use_doc_orientation_classify,
        )
    except TimeoutError:
        raise HTTPException(
            status_code=503,
            detail={"error": "server overloaded — try again shortly"},
            headers={"Retry-After": "5"},
        )

    return LayoutParsingResponse(**result)
