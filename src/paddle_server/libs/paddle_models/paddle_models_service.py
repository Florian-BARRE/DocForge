# ====== Code Summary ======
# PaddleModelsService: the model_server_core ModelService of the Paddle host. It aggregates the three
# pipelines the host serves — PP-StructureV3 (/layout-parsing), PaddleOCR (/ocr) and PaddleOCR-VL
# (/vl-parse) — so the core lifespan loads and unloads them as one, and GET /health reads one
# readiness. PP-StructureV3 and PaddleOCR are built at startup and gate readiness; PaddleOCR-VL is
# heavy and built LAZILY on its first request, so it is deliberately NOT part of the readiness gate
# (a deployment that never escalates to it never pays its download/load).

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from model_server_core import ModelService

# ====== Internal Project Imports ======
from libs.paddleocr import PaddleOcrService
from libs.paddleocr_vl import PaddleOcrVlService
from libs.ppstructure import PpStructureService


class PaddleModelsService(ModelService, LoggerClass):
    """
    The three Paddle pipelines behind one `ModelService`.

    Args:
        ppstructure (PpStructureService): The PP-StructureV3 layout pipeline (built at startup).
        paddleocr (PaddleOcrService): The OCR-only pipeline (built at startup).
        paddleocr_vl (PaddleOcrVlService): The PaddleOCR-VL pipeline (built lazily).
    """

    # Public attributes
    ppstructure: PpStructureService
    paddleocr: PaddleOcrService
    paddleocr_vl: PaddleOcrVlService

    def __init__(
        self,
        ppstructure: PpStructureService,
        paddleocr: PaddleOcrService,
        paddleocr_vl: PaddleOcrVlService,
    ) -> None:
        LoggerClass.__init__(self)
        self.ppstructure = ppstructure
        self.paddleocr = paddleocr
        self.paddleocr_vl = paddleocr_vl

    # =======================
    #   ModelService contract
    # =======================
    @property
    def ready(self) -> bool:
        """
        Returns:
            bool: True once BOTH eager pipelines (PP-StructureV3 and PaddleOCR) are built. The lazy
                PaddleOCR-VL pipeline never gates readiness.
        """
        return self.ppstructure.ready and self.paddleocr.ready

    def load(self) -> None:
        """Build the two eager pipelines, the slow step on first run (model download + load)."""
        # 1. PP-StructureV3: model download to the PADDLE_PDX_CACHE_HOME volume + weight load.
        self.logger.info("START build PP-StructureV3 pipeline (step 1/3)")
        self.ppstructure.load()

        # 2. PaddleOCR: the OCR-only capability, a SEPARATE instance from ppstructure.
        self.logger.info("START build PaddleOCR pipeline (step 2/3)")
        self.paddleocr.load()

        # 3. PaddleOCR-VL builds lazily on its first request; this only logs that.
        self.logger.info("PaddleOCR-VL pipeline (step 3/3)")
        self.paddleocr_vl.load()

    def unload(self) -> None:
        """Release every pipeline; each unload is a safe no-op when it was never built."""
        self.ppstructure.unload()
        self.paddleocr.unload()
        self.paddleocr_vl.unload()
