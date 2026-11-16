# ====== Code Summary ======
# Characterization (safety net) of POST /parse on the full app of the MinerU server: the raw-body guard
# (413), the input validation (422), the lock-wait timeout (503 + Retry-After), the 500, and a happy
# parse with a STUBBED engine (no MinerU / torch / CUDA) whose response is pinned to a committed golden.
# It records the behaviour of main so the shared-core extraction (R-27) cannot change it. The PARSE
# routes stayed byte-identical in step 3 (mineru adopts model_server_core); the one documented
# difference is the 500 of an unexpected exception: it was `{"detail": {"error": str(exc)}}`
# (leaking the exception text) and is now the core's typed body with a correlation id (see
# test_engine_failure_is_a_typed_500_that_hides_the_error_text). The app is driven without its lifespan.

# ====== Standard Library Imports ======
import json
from collections.abc import Iterator
from pathlib import Path

# ====== Third-Party Library Imports ======
import pytest
from fastapi.testclient import TestClient
from model_server_core import CORRELATION_ID_HEADER, INTERNAL_ERROR_MESSAGE

# ====== Internal Project Imports ======
from backend import MineruServer
from libs.mineru import MineruService
from tests.support.mineru_app import (
    MAX_BODY_BYTES,
    VALID_PDF,
    NeverAcquiredLock,
    StubEngine,
    build_server,
)

GOLDEN_PATH = Path(__file__).parent / "goldens" / "parse_response.json"


@pytest.fixture
def engine() -> StubEngine:
    return StubEngine()


@pytest.fixture
def server(engine: StubEngine, monkeypatch: pytest.MonkeyPatch) -> MineruServer:
    """A real MineruServer (validator, lock, normalizer) over a stubbed engine."""
    monkeypatch.setattr(MineruService, "_mineru_version", staticmethod(lambda: "9.9.9-test"))
    return build_server(engine)


@pytest.fixture
def client(server: MineruServer) -> TestClient:
    # raise_server_exceptions=False: the typed 500 is an HTTP answer the tests assert on, not an
    # exception to re-raise into the test client.
    return TestClient(server.create_app(), raise_server_exceptions=False)


# ── Happy path ───────────────────────────────────────────────────────────────


def test_parse_returns_the_recorded_sidecar_contract(
    client: TestClient, engine: StubEngine
) -> None:
    response = client.post("/parse", content=VALID_PDF, headers={"Content-Type": "application/pdf"})

    assert response.status_code == 200
    assert response.json() == json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def test_parse_hands_the_exact_request_bytes_to_the_engine(
    client: TestClient, engine: StubEngine
) -> None:
    client.post("/parse", content=VALID_PDF)

    assert engine.calls == [VALID_PDF]


def test_parse_page_count_falls_back_to_the_normalized_pages_when_the_engine_reports_zero(
    client: TestClient, engine: StubEngine
) -> None:
    engine.n_pages = 0

    response = client.post("/parse", content=VALID_PDF)

    assert response.status_code == 200
    assert response.json()["n_pages"] == len(response.json()["pages"]) == 2


def test_parse_engine_block_carries_the_pinned_model_id_and_backend(
    client: TestClient, engine: StubEngine
) -> None:
    engine_block = client.post("/parse", content=VALID_PDF).json()["engine"]

    assert engine_block == {
        "mineru": "9.9.9-test",
        "pipeline": "MinerU2.5-Pro-2605-1.2B",
        "backend": "vlm-transformers",
    }


def test_large_parse_response_is_gzip_compressed(client: TestClient, engine: StubEngine) -> None:
    engine.content_list = [
        {"type": "text", "text": "lorem ipsum " * 400, "page_idx": 0, "bbox": [0, 0, 100, 100]}
    ]
    engine.n_pages = 1

    response = client.post("/parse", content=VALID_PDF, headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"


# ── Request body guard (413) ─────────────────────────────────────────────────


def test_declared_content_length_over_the_cap_is_413_and_never_reaches_the_engine(
    client: TestClient, engine: StubEngine
) -> None:
    response = client.post("/parse", content=b"x" * (MAX_BODY_BYTES + 1))

    assert response.status_code == 413
    assert response.json() == {
        "detail": {"error": f"request body exceeds the {MAX_BODY_BYTES}-byte limit"}
    }
    assert engine.calls == []


def test_streamed_body_over_the_cap_without_content_length_is_413(
    client: TestClient, engine: StubEngine
) -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(MAX_BODY_BYTES // 256 + 2):
            yield b"x" * 256

    response = client.post("/parse", content=chunks())

    assert response.status_code == 413
    assert engine.calls == []


def test_body_exactly_at_the_cap_passes_the_guard(client: TestClient, engine: StubEngine) -> None:
    # Not a PDF, so it is refused by the validator (422), proving the guard let it through.
    response = client.post("/parse", content=b"x" * MAX_BODY_BYTES)

    assert response.status_code == 422


# ── Input validation (422) ───────────────────────────────────────────────────


def test_empty_body_is_422(client: TestClient, engine: StubEngine) -> None:
    response = client.post("/parse", content=b"")

    assert response.status_code == 422
    assert response.json() == {"detail": {"error": "empty request body"}}
    assert engine.calls == []


def test_undecodable_pdf_is_422_and_never_reaches_the_engine(
    client: TestClient, engine: StubEngine
) -> None:
    response = client.post("/parse", content=b"%PDF but truncated garbage")

    assert response.status_code == 422
    assert response.json() == {"detail": {"error": "request body is not a decodable PDF"}}
    assert engine.calls == []


# ── Saturation (503) and server faults (500) ─────────────────────────────────


def test_predict_lock_wait_timeout_is_503_with_retry_after(
    client: TestClient, engine: StubEngine, server: MineruServer
) -> None:
    server.service._lock = NeverAcquiredLock()  # type: ignore[assignment]

    response = client.post("/parse", content=VALID_PDF)

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    assert response.json() == {"detail": {"error": "server overloaded — try again shortly"}}
    assert engine.calls == []


def test_engine_failure_is_a_typed_500_that_hides_the_error_text(
    client: TestClient, engine: StubEngine
) -> None:
    """R-27 (approved behaviour change): the 500 body is a generic typed error plus a correlation id,
    never `str(exc)` (was `{"detail": {"error": "cuda out of memory"}}`)."""
    engine.failure = RuntimeError("cuda out of memory")

    response = client.post("/parse", content=VALID_PDF)

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["error"] == INTERNAL_ERROR_MESSAGE
    assert detail["correlation_id"] == response.headers[CORRELATION_ID_HEADER]
    assert "cuda out of memory" not in response.text


def test_predict_lock_is_released_after_an_engine_failure(
    client: TestClient, engine: StubEngine
) -> None:
    engine.failure = RuntimeError("boom")
    assert client.post("/parse", content=VALID_PDF).status_code == 500

    engine.failure = None
    assert client.post("/parse", content=VALID_PDF).status_code == 200


# ── Routing ──────────────────────────────────────────────────────────────────


def test_parse_only_accepts_post(client: TestClient) -> None:
    assert client.get("/parse").status_code == 405
