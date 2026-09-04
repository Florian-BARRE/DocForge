# ====== Code Summary ======
# Unit tests for RequestBodyGuard.read_capped — the OOM guard on the raw-body routes. Proves a
# declared Content-Length over the cap is refused before any byte is read, a lying/absent length is
# still caught by the streamed cap, a body under the cap is returned intact, and a malformed
# Content-Length falls through to the streamed cap. Uses a fake request (no server needed).

# ====== Standard Library Imports ======
from collections.abc import AsyncIterator

# ====== Third-Party Library Imports ======
import pytest
from fastapi import HTTPException

# ====== Internal Project Imports ======
from backend.libs.utils.request_limits import RequestBodyGuard


class _FakeRequest:
    """A minimal stand-in for a Starlette Request — only .headers and .stream() are touched."""

    def __init__(self, body: bytes, *, content_length: str | None = "auto", chunk: int = 4) -> None:
        self._body = body
        length = str(len(body)) if content_length == "auto" else content_length
        self.headers = {} if length is None else {"content-length": length}
        self._chunk = chunk
        self.streamed = False

    async def stream(self) -> AsyncIterator[bytes]:
        self.streamed = True
        for i in range(0, len(self._body), self._chunk):
            yield self._body[i : i + self._chunk]


async def test_body_under_cap_is_returned_intact() -> None:
    request = _FakeRequest(b"hello world")
    got = await RequestBodyGuard.read_capped(request, max_bytes=1024)  # type: ignore[arg-type]
    assert got == b"hello world"


async def test_declared_content_length_over_cap_is_refused_before_reading() -> None:
    request = _FakeRequest(b"x" * 100, content_length="1000000")
    with pytest.raises(HTTPException) as exc:
        await RequestBodyGuard.read_capped(request, max_bytes=50)  # type: ignore[arg-type]
    assert exc.value.status_code == 413
    # The fast path rejects on the header alone — the body stream is never consumed.
    assert request.streamed is False


async def test_streamed_size_over_cap_is_refused_when_length_lies() -> None:
    # Content-Length claims a small size, but the actual stream is large — the running cap catches it.
    request = _FakeRequest(b"x" * 200, content_length="10")
    with pytest.raises(HTTPException) as exc:
        await RequestBodyGuard.read_capped(request, max_bytes=50)  # type: ignore[arg-type]
    assert exc.value.status_code == 413
    assert request.streamed is True


async def test_absent_content_length_is_still_capped_by_the_stream() -> None:
    request = _FakeRequest(b"x" * 200, content_length=None)
    with pytest.raises(HTTPException) as exc:
        await RequestBodyGuard.read_capped(request, max_bytes=50)  # type: ignore[arg-type]
    assert exc.value.status_code == 413


async def test_malformed_content_length_falls_through_to_the_streamed_cap() -> None:
    # A non-integer header must not crash — it is ignored and the streamed cap governs.
    request = _FakeRequest(b"x" * 10, content_length="not-a-number")
    got = await RequestBodyGuard.read_capped(request, max_bytes=1024)  # type: ignore[arg-type]
    assert got == b"x" * 10
