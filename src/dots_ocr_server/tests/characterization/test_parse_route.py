# ====== Code Summary ======
# Characterization (safety net) of POST /parse on the full create_app() of the dots.ocr server: the
# raw-body guard (413), the input validation (422), the lock-wait timeout (503 + Retry-After), the
# non-leaky 500, and a happy parse with a STUBBED engine (no dots.ocr / torch / CUDA) whose response is
# pinned to a committed golden. It records TODAY's behaviour on main so the planned shared-core
# extraction of the request guard / error handling / service lock cannot change it: a failing test
# here is a refactor decision to review, not a test to fix. The app is driven without its lifespan.

# ====== Standard Library Imports ======
import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

# ====== Third-Party Library Imports ======
import pytest
from fastapi.testclient import TestClient

# ====== Internal Project Imports ======
from backend.app import create_app
from backend.context import CONTEXT
from libs.dots_ocr import DotsOcrService

GOLDEN_PATH = Path(__file__).parent / "goldens" / "parse_response.json"
PAGE_ELEMENTS = (Path(__file__).parents[1] / "fixtures" / "dots_ocr_page.json").read_text(
    encoding="utf-8"
)
MODEL_PATH = "rednote-hilab/dots.ocr"

# A structurally-valid single-page PDF (catalog -> pages -> one empty page): enough for pypdfium2 to
# count a page, which is all InputValidator.verify_pdf needs before the (stubbed) engine runs.
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


class _StubConfig:
    """Minimal stand-in for DotsOcrServerConfig: only what the /parse route reads."""

    DOTS_OCR_MAX_BODY_BYTES = MAX_BODY_BYTES


class _StubEngine:
    """Stands in for DotsOcrEngine.analyze: records the bytes it got, returns canned page outputs."""

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


class _NeverAcquiredLock:
    """A predict lock that is always held by someone else: acquire() never completes."""

    async def acquire(self) -> bool:
        await asyncio.Event().wait()
        return True

    def release(self) -> None:  # pragma: no cover - never reached, acquire never returns
        raise AssertionError("release() called on a lock that was never acquired")


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> _StubEngine:
    """A real DotsOcrService (validator, lock, normalizer) over a stubbed engine, wired in CONTEXT."""
    service = DotsOcrService(
        model_path=MODEL_PATH,
        model_cache_home="/models",
        render_dpi=200,
        max_pages=0,
        max_tokens=16384,
        image_factor=28,
        min_pixels=3136,
        max_pixels=11289600,
        lock_wait_timeout_seconds=LOCK_WAIT_SECONDS,
    )
    stub = _StubEngine()
    monkeypatch.setattr(service, "_engine", stub, raising=True)
    monkeypatch.setattr(DotsOcrService, "_transformers_version", staticmethod(lambda: "9.9.9-test"))
    monkeypatch.setattr(CONTEXT, "CONFIG", _StubConfig, raising=False)
    monkeypatch.setattr(CONTEXT, "dots_ocr", service, raising=False)
    return stub


@pytest.fixture
def client(engine: _StubEngine) -> TestClient:
    return TestClient(create_app())


# ── Happy path ───────────────────────────────────────────────────────────────


def test_parse_returns_the_recorded_sidecar_contract(
    client: TestClient, engine: _StubEngine
) -> None:
    response = client.post("/parse", content=VALID_PDF, headers={"Content-Type": "application/pdf"})

    assert response.status_code == 200
    assert response.json() == json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def test_parse_hands_the_exact_request_bytes_to_the_engine(
    client: TestClient, engine: _StubEngine
) -> None:
    client.post("/parse", content=VALID_PDF)

    assert engine.calls == [VALID_PDF]


def test_parse_page_count_falls_back_to_the_normalized_pages_when_the_engine_reports_zero(
    client: TestClient, engine: _StubEngine
) -> None:
    engine.n_pages = 0

    response = client.post("/parse", content=VALID_PDF)

    assert response.status_code == 200
    assert response.json()["n_pages"] == len(response.json()["pages"]) == 2


def test_parse_engine_block_carries_the_model_path_and_transformers_backend(
    client: TestClient, engine: _StubEngine
) -> None:
    engine_block = client.post("/parse", content=VALID_PDF).json()["engine"]

    assert engine_block == {
        "dots_ocr": "9.9.9-test",
        "model": MODEL_PATH,
        "backend": "transformers",
    }


def test_large_parse_response_is_gzip_compressed(client: TestClient, engine: _StubEngine) -> None:
    long_text = json.dumps(
        [{"category": "Text", "bbox": [0, 0, 100, 100], "reading_order": 0, "text": "lorem " * 400}]
    )
    engine.page_outputs = [
        {"page_index": 0, "image_width": 800, "image_height": 600, "raw_output": long_text}
    ]
    engine.n_pages = 1

    response = client.post("/parse", content=VALID_PDF, headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"


# ── Request body guard (413) ─────────────────────────────────────────────────


def test_declared_content_length_over_the_cap_is_413_and_never_reaches_the_engine(
    client: TestClient, engine: _StubEngine
) -> None:
    response = client.post("/parse", content=b"x" * (MAX_BODY_BYTES + 1))

    assert response.status_code == 413
    assert response.json() == {
        "detail": {"error": f"request body exceeds the {MAX_BODY_BYTES}-byte limit"}
    }
    assert engine.calls == []


def test_streamed_body_over_the_cap_without_content_length_is_413(
    client: TestClient, engine: _StubEngine
) -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(MAX_BODY_BYTES // 256 + 2):
            yield b"x" * 256

    response = client.post("/parse", content=chunks())

    assert response.status_code == 413
    assert engine.calls == []


def test_body_exactly_at_the_cap_passes_the_guard(client: TestClient, engine: _StubEngine) -> None:
    # Not a PDF, so it is refused by the validator (422), proving the guard let it through.
    response = client.post("/parse", content=b"x" * MAX_BODY_BYTES)

    assert response.status_code == 422


# ── Input validation (422) ───────────────────────────────────────────────────


def test_empty_body_is_422(client: TestClient, engine: _StubEngine) -> None:
    response = client.post("/parse", content=b"")

    assert response.status_code == 422
    assert response.json() == {"detail": {"error": "empty request body"}}
    assert engine.calls == []


def test_undecodable_pdf_is_422_and_never_reaches_the_engine(
    client: TestClient, engine: _StubEngine
) -> None:
    response = client.post("/parse", content=b"%PDF but truncated garbage")

    assert response.status_code == 422
    assert response.json() == {"detail": {"error": "request body is not a decodable PDF"}}
    assert engine.calls == []


# ── Saturation (503) and server faults (500) ─────────────────────────────────


def test_predict_lock_wait_timeout_is_503_with_retry_after(
    client: TestClient, engine: _StubEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(CONTEXT.dots_ocr, "_lock", _NeverAcquiredLock())

    response = client.post("/parse", content=VALID_PDF)

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    assert response.json() == {"detail": {"error": "server overloaded — try again shortly"}}
    assert engine.calls == []


def test_engine_failure_is_a_500_carrying_the_error_text(
    client: TestClient, engine: _StubEngine
) -> None:
    engine.failure = RuntimeError("cuda out of memory")

    response = client.post("/parse", content=VALID_PDF)

    assert response.status_code == 500
    assert response.json() == {"detail": {"error": "cuda out of memory"}}


def test_predict_lock_is_released_after_an_engine_failure(
    client: TestClient, engine: _StubEngine
) -> None:
    engine.failure = RuntimeError("boom")
    assert client.post("/parse", content=VALID_PDF).status_code == 500

    engine.failure = None
    assert client.post("/parse", content=VALID_PDF).status_code == 200


# ── Routing ──────────────────────────────────────────────────────────────────


def test_parse_only_accepts_post(client: TestClient) -> None:
    assert client.get("/parse").status_code == 405
