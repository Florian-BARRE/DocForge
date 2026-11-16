# ====== Code Summary ======
# Route definition for POST /vl-parse — the PaddleOCR-VL 1.6 sidecar endpoint. Raw PDF bytes in, the
# SAME clean reading-ordered per-page block contract /layout-parsing returns out (it reuses that
# route's LayoutParsingResponse model on purpose — an identical wire shape means the DocForge IR
# mapper is shared). The pipeline is built LAZILY inside PaddleOcrVlService.parse_pdf on the first
# request, so this route pays the model download/load once (surfaced as a slow first response), never
# at startup. Sub-pipeline toggles are optional query params overriding the pipeline defaults. The
# body is read under the core RequestBodyGuard (413 over the cap, 422 when empty) and checked by the
# core InputValidator (422 for an undecodable PDF, through the core InvalidInputError handler); a
# lock-wait timeout is translated to HTTP 503. Any other exception is turned into the typed 500 by the
# core ServerErrorHandler: no catch-all here.

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, HTTPException, Request
from loggerplusplus import LoggerClass
from model_server_core import InputValidator, RequestBodyGuard

# ====== Internal Project Imports ======
from libs.paddleocr_vl import PaddleOcrVlService

# ====== Local Project Imports ======
from ..layout_parsing.models import LayoutParsingResponse

# Seconds a saturated caller is told to wait before retrying (Retry-After of the 503).
RETRY_AFTER_SECONDS = "5"


class VlParsingRoutes(LoggerClass):
    """
    The POST /vl-parse route of the Paddle host, bound to its PaddleOCR-VL service and the core
    request guards.

    Per-request tracing goes through this class's logger at DEBUG level — request sizes only, never
    file contents.

    Args:
        service (PaddleOcrVlService): The lazily built PaddleOCR-VL pipeline service.
        body_guard (RequestBodyGuard): Reads the raw body under the `MAX_BODY_BYTES` ceiling.
        input_validator (InputValidator): Checks the body decodes as a PDF before any inference.
    """

    # Public attributes
    router: APIRouter

    def __init__(
        self,
        service: PaddleOcrVlService,
        body_guard: RequestBodyGuard,
        input_validator: InputValidator,
    ) -> None:
        LoggerClass.__init__(self)
        self._service = service
        self._body_guard = body_guard
        self._input_validator = input_validator
        self.router = APIRouter()
        self.router.add_api_route(
            "/vl-parse", self.vl_parse, methods=["POST"], response_model=LayoutParsingResponse
        )

    async def vl_parse(
        self,
        request: Request,
        use_chart_recognition: bool | None = None,
        use_seal_recognition: bool | None = None,
        use_ocr_for_image_block: bool | None = None,
    ) -> LayoutParsingResponse:
        # NOTE: the docstring below is published as the OpenAPI description of POST /vl-parse, which
        # is pinned byte-identical by the characterization golden: keep it free of implementation
        # notes.
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
        # 1. Read the raw body under the hard size cap — the request IS the PDF. An oversized upload
        #    is refused 413 (before/while buffering) instead of OOMing the container; an empty one is
        #    422.
        pdf_bytes = await self._body_guard.read_non_empty(request)
        self.logger.debug(f"POST /vl-parse: {len(pdf_bytes)} bytes")

        # 2. Reject an undecodable PDF as a client error BEFORE the lazy build or any inference.
        self._input_validator.verify_pdf(pdf_bytes)

        # 3. Delegate to the lazy pipeline service; a lock-wait timeout means the service is
        #    saturated -> 503 with Retry-After. Any other failure is a genuine server fault (typed 500
        #    from the core).
        try:
            result = await self._service.parse_pdf(
                pdf_bytes,
                use_chart_recognition=use_chart_recognition,
                use_seal_recognition=use_seal_recognition,
                use_ocr_for_image_block=use_ocr_for_image_block,
            )
        except TimeoutError:
            raise HTTPException(
                status_code=503,
                detail={"error": "server overloaded — try again shortly"},
                headers={"Retry-After": RETRY_AFTER_SECONDS},
            )

        return LayoutParsingResponse(**result)
