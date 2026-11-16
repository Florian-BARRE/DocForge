# ====== Code Summary ======
# Test seam shared by the paddle_server tests: builds the real PaddleServer (no lifespan, so no pipeline
# loads) and swaps its three pipeline services for fakes, so a route, /health or the whole app can be
# driven through a TestClient without PaddlePaddle. Also holds the PDF / image fixtures and the config
# variants the tests inject (a tiny body cap, a short lock wait).

# ====== Standard Library Imports ======
import io
from typing import Any

# ====== Third-Party Library Imports ======
from model_server_core import ModelService

# ====== Internal Project Imports ======
from backend import PaddleServer
from config_loader import PaddleServerConfig
from libs.paddle_models import PaddleModelsService

# A structurally-valid single-page PDF (catalog -> pages -> one empty page): enough for pypdfium2 to
# count a page, which is all the core PdfDecoder needs before the (stubbed) service runs.
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


def valid_png_bytes() -> bytes:
    """Build a tiny valid PNG in memory (Pillow is a hard transitive dependency)."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (255, 255, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


class SmallLimitsConfig(PaddleServerConfig):
    """A configuration with a tiny body cap and a short predict-lock wait, so the guards trip fast."""

    MAX_BODY_BYTES = MAX_BODY_BYTES
    LOCK_WAIT_TIMEOUT_SECONDS = LOCK_WAIT_SECONDS


class FakePipeline(ModelService):
    """A pipeline service that records its lifecycle instead of building a paddle pipeline.

    Args:
        ready (bool): The readiness it reports (a built pipeline is ready).
    """

    def __init__(self, ready: bool = True) -> None:
        self._ready = ready
        self.calls: list[str] = []

    @property
    def ready(self) -> bool:
        """Whether the fake pipeline reports itself built."""
        return self._ready

    def load(self) -> None:
        """Record the build and become ready."""
        self.calls.append("load")
        self._ready = True

    def unload(self) -> None:
        """Record the release and become not ready."""
        self.calls.append("unload")
        self._ready = False


def build_server(
    ppstructure: Any | None = None,
    paddleocr: Any | None = None,
    paddleocr_vl: Any | None = None,
    config: type[PaddleServerConfig] = SmallLimitsConfig,
) -> PaddleServer:
    """Assemble a PaddleServer whose three pipelines are the given fakes.

    Args:
        ppstructure (Any | None): Fake PP-StructureV3 service (None: the real, unbuilt one).
        paddleocr (Any | None): Fake PaddleOCR service (None: the real, unbuilt one).
        paddleocr_vl (Any | None): Fake PaddleOCR-VL service (None: the real, unbuilt one).
        config (type[PaddleServerConfig]): The configuration to inject.

    Returns:
        PaddleServer: The server; call `create_app()` on it.
    """
    server = PaddleServer(config)
    server.ppstructure = ppstructure or server.ppstructure
    server.paddleocr = paddleocr or server.paddleocr
    server.paddleocr_vl = paddleocr_vl or server.paddleocr_vl
    server.models = PaddleModelsService(server.ppstructure, server.paddleocr, server.paddleocr_vl)
    return server
