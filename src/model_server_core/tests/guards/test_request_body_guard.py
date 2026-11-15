# ====== Code Summary ======
# Behaviour of RequestBodyGuard through a real route: bodies up to the cap pass, a declared or streamed
# overflow is a 413 (even with a lying or absent Content-Length), an empty body is a 422.

# ====== Standard Library Imports ======
from collections.abc import Iterator

# ====== Third-Party Library Imports ======
import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

# ====== Internal Project Imports ======
from model_server_core import RequestBodyGuard

CAP = 8


def _client() -> TestClient:
    guard = RequestBodyGuard(max_bytes=CAP)
    app = FastAPI()

    @app.post("/capped")
    async def capped(request: Request) -> dict[str, int]:
        return {"size": len(await guard.read_capped(request))}

    @app.post("/required")
    async def required(body: bytes = Depends(guard.read_non_empty)) -> dict[str, int]:
        return {"size": len(body)}

    return TestClient(app)


def _chunks(*parts: bytes) -> Iterator[bytes]:
    yield from parts


def test_body_under_the_cap_is_read_whole() -> None:
    response = _client().post("/capped", content=b"1234")

    assert response.status_code == 200
    assert response.json() == {"size": 4}


def test_body_exactly_at_the_cap_passes() -> None:
    assert _client().post("/capped", content=b"x" * CAP).status_code == 200


def test_declared_content_length_over_the_cap_is_refused_before_reading() -> None:
    response = _client().post("/capped", content=b"x" * (CAP + 1))

    assert response.status_code == 413
    assert response.json() == {"detail": {"error": f"request body exceeds the {CAP}-byte limit"}}


def test_streamed_body_without_content_length_is_still_capped() -> None:
    response = _client().post("/capped", content=_chunks(b"x" * 5, b"y" * 5))

    assert response.status_code == 413


def test_lying_content_length_cannot_bypass_the_streamed_cap() -> None:
    response = _client().post(
        "/capped", content=_chunks(b"x" * 5, b"y" * 5), headers={"content-length": "3"}
    )

    assert response.status_code == 413


def test_malformed_content_length_falls_back_to_the_streamed_cap() -> None:
    ok = _client().post("/capped", content=b"1234", headers={"content-length": "not-a-number"})
    too_big = _client().post(
        "/capped", content=b"x" * (CAP + 1), headers={"content-length": "not-a-number"}
    )

    assert ok.status_code == 200
    assert too_big.status_code == 413


def test_read_non_empty_rejects_an_empty_body_with_422() -> None:
    response = _client().post("/required", content=b"")

    assert response.status_code == 422
    assert response.json() == {"detail": {"error": "empty request body"}}


def test_read_non_empty_still_applies_the_cap() -> None:
    assert _client().post("/required", content=b"x" * (CAP + 1)).status_code == 413


def test_read_non_empty_returns_the_body() -> None:
    assert _client().post("/required", content=b"abc").json() == {"size": 3}


@pytest.mark.parametrize("bad", [0, -1])
def test_guard_refuses_a_non_positive_cap(bad: int) -> None:
    with pytest.raises(ValueError, match="max_bytes"):
        RequestBodyGuard(max_bytes=bad)
