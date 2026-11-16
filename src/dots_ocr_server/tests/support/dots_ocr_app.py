# ====== Code Summary ======
# Test seam shared by the dots_ocr_server tests: builds the real DotsOcrServer (no lifespan, so nothing
# loads) and swaps its engine for a stub, so /parse, /health or the whole app can be driven through a
# TestClient without dots.ocr, transformers, torch or CUDA. Also holds the PDF fixtures and the config
# variants the tests inject (a tiny body cap, a short lock wait).

# ====== Standard Library Imports ======
import asyncio
from pathlib import Path
from typing import Any

# ====== Internal Project Imports ======
from backend import DotsOcrServer
from config_loader import DotsOcrServerConfig

PAGE_ELEMENTS = (Path(__file__).parents[1] / "fixtures" / "dots_ocr_page.json").read_text(
    encoding="utf-8"
)
MODEL_PATH = "rednote-hilab/dots.ocr"

# A structurally-valid single-page PDF (catalog -> pages -> one empty page): enough for pypdfium2 to
# count a page, which is all the core PdfDecoder needs before the (stubbed) engine runs.
VALID_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
    b"0000000052 00000 n \n0000000101 00000 n \n"
    b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n170\n%%EOF"
)

MAX_BODY_BYTES = 2048
LOCK_WAIT_SECONDS = 0.05


class SmallLimitsConfig(DotsOcrServerConfig):
    """A configuration with a tiny body cap and a short predict-lock wait, so the guards trip fast."""

    MAX_BODY_BYTES = MAX_BODY_BYTES
    LOCK_WAIT_TIMEOUT_SECONDS = LOCK_WAIT_SECONDS


class StubEngine:
    """Stands in for DotsOcrEngine: records the bytes it got, returns canned page outputs."""

    model_path = MODEL_PATH

    def __init__(self) -> None:
        self.calls: list[bytes] = []
        self.page_outputs: list[dict[str, Any]] = [
            {
                "page_index": index,
                "image_width": 1224,
                "image_height": 1584,
                "raw_output": PAGE_ELEMENTS,
            }
            for index in range(2)
        ]
        self.n_pages = 2
        self.failure: Exception | None = None

    def analyze(self, pdf_bytes: bytes) -> tuple[list[dict[str, Any]], int]:
        self.calls.append(pdf_bytes)
        if self.failure is not None:
            raise self.failure
        return self.page_outputs, self.n_pages

    def unload(self) -> None:
        """Nothing was loaded."""


class NeverAcquiredLock:
    """A predict lock that is always held by someone else: acquire() never completes."""

    async def acquire(self) -> bool:
        await asyncio.Event().wait()
        return True

    def release(self) -> None:  # pragma: no cover - never reached, acquire never returns
        raise AssertionError("release() called on a lock that was never acquired")


def build_server(
    engine: StubEngine | None = None,
    config: type[DotsOcrServerConfig] = SmallLimitsConfig,
) -> DotsOcrServer:
    """Assemble a DotsOcrServer whose parse service runs over the given stub engine.

    Args:
        engine (StubEngine | None): The stub engine (None: the real, unloaded one).
        config (type[DotsOcrServerConfig]): The configuration to inject.

    Returns:
        DotsOcrServer: The server; call `create_app()` on it.
    """
    server = DotsOcrServer(config)
    if engine is not None:
        server.service._engine = engine  # type: ignore[assignment]
    return server
