# ====== Code Summary ======
# Route definition for POST /layout-parsing — the sidecar's OWN contract (see models.py). Raw PDF
# bytes in, a clean reading-ordered per-page block list out. Sub-pipeline toggles are optional query
# params that override the pipeline-level defaults for this one request; `use_doc_unwarping` is
# intentionally NOT exposed here (always False — see libs/ppstructure/service.py). The body is read
# under the core RequestBodyGuard (413 over the cap, 422 when empty) and checked by the core
# InputValidator (422 for an undecodable PDF, through the core InvalidInputError handler); all
# inference is delegated to PpStructureService and a lock-wait timeout is translated to HTTP 503. Any
# other exception is turned into the typed 500 by the core ServerErrorHandler: no catch-all here.

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, HTTPException, Request
from loggerplusplus import LoggerClass
from model_server_core import InputValidator, RequestBodyGuard

# ====== Internal Project Imports ======
from libs.ppstructure import PpStructureService

# ====== Local Project Imports ======
from .models import LayoutParsingResponse

# Seconds a saturated caller is told to wait before retrying (Retry-After of the 503).
RETRY_AFTER_SECONDS = "5"


class LayoutParsingRoutes(LoggerClass):
    """
    The POST /layout-parsing route of the Paddle host, bound to its PP-StructureV3 service and the
    core request guards.

    Per-request tracing goes through this class's logger at DEBUG level — request sizes only, never
    file contents.

    Args:
        service (PpStructureService): The PP-StructureV3 pipeline service (owns the predict lock).
        body_guard (RequestBodyGuard): Reads the raw body under the `MAX_BODY_BYTES` ceiling.
        input_validator (InputValidator): Checks the body decodes as a PDF before any inference.
    """

    # Public attributes
    router: APIRouter

    def __init__(
        self,
        service: PpStructureService,
        body_guard: RequestBodyGuard,
        input_validator: InputValidator,
    ) -> None:
        LoggerClass.__init__(self)
        self._service = service
        self._body_guard = body_guard
        self._input_validator = input_validator
        self.router = APIRouter()
        self.router.add_api_route(
            "/layout-parsing",
            self.layout_parsing,
            methods=["POST"],
            response_model=LayoutParsingResponse,
        )

    async def layout_parsing(
        self,
        request: Request,
        use_table_recognition: bool | None = None,
        use_formula_recognition: bool | None = None,
        use_seal_recognition: bool | None = None,
        use_doc_orientation_classify: bool | None = None,
    ) -> LayoutParsingResponse:
        # NOTE: the docstring below is published as the OpenAPI description of POST /layout-parsing,
        # which is pinned byte-identical by the characterization golden: keep it free of
        # implementation notes.
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
        # 1. Read the raw body under the hard size cap — no pydantic model, the request IS the PDF.
        #    An oversized upload is refused 413 (before/while buffering) instead of OOMing the
        #    container; an empty one is 422.
        pdf_bytes = await self._body_guard.read_non_empty(request)
        self.logger.debug(f"POST /layout-parsing: {len(pdf_bytes)} bytes")

        # 2. Reject an undecodable PDF as a client error BEFORE taking the lock or spending inference.
        self._input_validator.verify_pdf(pdf_bytes)

        # 3. Delegate to the pipeline service; a lock-wait timeout means the service is saturated ->
        #    503 with Retry-After. Any other failure is a genuine server fault (typed 500 from the core).
        try:
            result = await self._service.parse_pdf(
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
                headers={"Retry-After": RETRY_AFTER_SECONDS},
            )

        return LayoutParsingResponse(**result)
