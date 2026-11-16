# ====== Code Summary ======
# Test seam shared by the mineru_server tests: builds the real MineruServer (no lifespan, so nothing
# loads) and swaps its engine for a stub, so /parse, /health or the whole app can be driven through a
# TestClient without MinerU, torch or CUDA. Also holds the PDF fixtures and the config variants the
# tests inject (a tiny body cap, a short lock wait).

# ====== Standard Library Imports ======
import asyncio
import json
from pathlib import Path
from typing import Any

# ====== Internal Project Imports ======
from backend import MineruServer
from config_loader import MineruServerConfig

CONTENT_LIST = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "content_list.json").read_text(encoding="utf-8")
)

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


class SmallLimitsConfig(MineruServerConfig):
    """A configuration with a tiny body cap and a short predict-lock wait, so the guards trip fast."""

    MAX_BODY_BYTES = MAX_BODY_BYTES
    LOCK_WAIT_TIMEOUT_SECONDS = LOCK_WAIT_SECONDS


class StubEngine:
    """Stands in for MineruEngine: records the bytes it got, returns a canned content_list."""

    backend = "vlm-transformers"

    def __init__(self) -> None:
        self.calls: list[bytes] = []
        self.content_list: list[dict[str, Any]] = CONTENT_LIST
        self.n_pages = 2
        self.failure: Exception | None = None

    def analyze(self, pdf_bytes: bytes) -> tuple[list[dict[str, Any]], int]:
        self.calls.append(pdf_bytes)
        if self.failure is not None:
            raise self.failure
        return self.content_list, self.n_pages

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
    config: type[MineruServerConfig] = SmallLimitsConfig,
) -> MineruServer:
    """Assemble a MineruServer whose parse service runs over the given stub engine.

    Args:
        engine (StubEngine | None): The stub engine (None: the real, unloaded one).
        config (type[MineruServerConfig]): The configuration to inject.

    Returns:
        MineruServer: The server; call `create_app()` on it.
    """
    server = MineruServer(config)
    if engine is not None:
        server.service._engine = engine  # type: ignore[assignment]
    return server
