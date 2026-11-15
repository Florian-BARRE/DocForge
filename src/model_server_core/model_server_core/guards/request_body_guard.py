# ====== Code Summary ======
# RequestBodyGuard: bounds how many bytes a raw-body route will buffer. Such a route reads the WHOLE
# body into memory (the body IS the image/PDF), so an uncapped request is an OOM vector against a
# container whose memory ceiling exists for model spikes, not attacker payloads. The guard refuses a
# declared Content-Length over the cap before reading a byte, then caps the streamed read so a lying
# or absent length cannot bypass it (413). An empty body is a client error (422).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import NoReturn

# ====== Third-Party Library Imports ======
from fastapi import HTTPException, Request
from loggerplusplus import LoggerClass


class RequestBodyGuard(LoggerClass):
    """Reads a request body under a hard byte ceiling.

    Args:
        max_bytes (int): The hard ceiling in bytes (`ServerConfig.MAX_BODY_BYTES`).

    Raises:
        ValueError: If `max_bytes` is not positive.
    """

    # Public attributes
    max_bytes: int

    def __init__(self, *, max_bytes: int) -> None:
        LoggerClass.__init__(self)
        if max_bytes < 1:
            raise ValueError(f"max_bytes must be >= 1, got {max_bytes}")
        self.max_bytes = max_bytes

    # =======================
    #   Private Methods
    # =======================
    def _reject(self) -> NoReturn:
        """Log and raise the 413 for a body that crosses the ceiling."""
        self.logger.warning(f"Rejected request body exceeding {self.max_bytes} bytes")
        raise HTTPException(
            status_code=413,
            detail={"error": f"request body exceeds the {self.max_bytes}-byte limit"},
        )

    def _check_declared_length(self, request: Request) -> None:
        """Refuse a declared Content-Length over the cap before any byte is read."""
        declared = request.headers.get("content-length")
        if declared is None:
            return
        try:
            too_large = int(declared) > self.max_bytes
        except ValueError:
            # Malformed header: the streamed cap in `read_capped` still bounds the read.
            return
        if too_large:
            self._reject()

    # =======================
    #   Public Methods
    # =======================
    async def read_capped(self, request: Request) -> bytes:
        """Read the full request body, refusing (413) as soon as it would exceed the cap.

        Args:
            request (Request): The incoming request whose raw body is the payload.

        Returns:
            bytes: The buffered body (at most `max_bytes`).

        Raises:
            HTTPException: 413 when the declared Content-Length OR the streamed size is over the cap.
        """
        # 1. Fast path: a declared Content-Length over the cap is refused before any byte is read.
        self._check_declared_length(request)

        # 2. Stream with a running total so a lying or absent Content-Length cannot bypass the cap.
        chunks: list[bytes] = []
        total = 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > self.max_bytes:
                self._reject()
            chunks.append(chunk)
        return b"".join(chunks)

    async def read_non_empty(self, request: Request) -> bytes:
        """Read the capped body and refuse (422) an empty one.

        Usable directly as a FastAPI dependency: `body: bytes = Depends(guard.read_non_empty)`.

        Args:
            request (Request): The incoming request whose raw body is the payload.

        Returns:
            bytes: The buffered, non-empty body.

        Raises:
            HTTPException: 413 over the cap, 422 when the body is empty.
        """
        body = await self.read_capped(request)
        if not body:
            raise HTTPException(status_code=422, detail={"error": "empty request body"})
        return body
