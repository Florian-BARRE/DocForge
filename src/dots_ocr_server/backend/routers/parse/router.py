# ====== Code Summary ======
# Route definition for POST /parse — the dots.ocr sidecar endpoint. Raw PDF bytes in, the shared
# reading-ordered per-page block contract out (the SAME shape mineru_server's /parse returns, so the
# DocForge IR mapper family is shared). The dots.ocr VLM model is loaded LAZILY inside
# DotsOcrService.parse_pdf on the first request, so this route pays the model download/load once (a
# slow first response), never at startup. The body is read under the core RequestBodyGuard (413 over the
# cap, 422 when empty) and checked by the core InputValidator (422 for an undecodable PDF, through the
# core InvalidInputError handler); a lock-wait timeout is translated to HTTP 503. Any other exception is
# turned into the typed 500 by the core ServerErrorHandler: no catch-all here.

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, HTTPException, Request
from loggerplusplus import LoggerClass
from model_server_core import InputValidator, RequestBodyGuard

# ====== Internal Project Imports ======
from libs.dots_ocr import DotsOcrService

# ====== Local Project Imports ======
from .models import ParseResponse

# Seconds a saturated caller is told to wait before retrying (Retry-After of the 503).
RETRY_AFTER_SECONDS = "5"


class ParseRoutes(LoggerClass):
    """
    The POST /parse route of the dots.ocr host, bound to its parse service and the core request guards.

    Per-request tracing goes through this class's logger at DEBUG level — request sizes only, never
    file contents.

    Args:
        service (DotsOcrService): The parse service (owns the predict lock and the engine).
        body_guard (RequestBodyGuard): Reads the raw body under the `MAX_BODY_BYTES` ceiling.
        input_validator (InputValidator): Checks the body decodes as a PDF before any inference.
    """

    # Public attributes
    router: APIRouter

    def __init__(
        self,
        service: DotsOcrService,
        body_guard: RequestBodyGuard,
        input_validator: InputValidator,
    ) -> None:
        LoggerClass.__init__(self)
        self._service = service
        self._body_guard = body_guard
        self._input_validator = input_validator
        self.router = APIRouter()
        self.router.add_api_route(
            "/parse", self.parse, methods=["POST"], response_model=ParseResponse
        )

    async def parse(self, request: Request) -> ParseResponse:
        # NOTE: the docstring below is published as the OpenAPI description of POST /parse, which is
        # pinned byte-identical by the characterization golden: keep it free of implementation notes.
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
        # 1. Read the raw body under the hard size cap — the request IS the PDF. An oversized upload is
        #    refused 413 (before/while buffering) instead of OOMing the container; an empty one is 422.
        pdf_bytes = await self._body_guard.read_non_empty(request)
        self.logger.debug(f"POST /parse: {len(pdf_bytes)} bytes")

        # 2. Reject an undecodable PDF as a client error BEFORE spending inference.
        self._input_validator.verify_pdf(pdf_bytes)

        # 3. Delegate to the parse service; a lock-wait timeout means the service is saturated -> 503
        #    with Retry-After. Any other failure is a genuine server fault (typed 500 from the core).
        try:
            result = await self._service.parse_pdf(pdf_bytes)
        except TimeoutError:
            raise HTTPException(
                status_code=503,
                detail={"error": "server overloaded — try again shortly"},
                headers={"Retry-After": RETRY_AFTER_SECONDS},
            )

        return ParseResponse(**result)
