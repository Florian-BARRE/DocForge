# ====== Code Summary ======
# RequestBodyGuard — bounds how many bytes a raw-body route (/ocr, /layout-parsing) will buffer. Both
# routes read the WHOLE body into memory (the body IS the image/PDF), so an uncapped request is an OOM
# vector against a container whose memory ceiling exists for model spikes, not attacker payloads. The
# guard refuses a declared Content-Length over the cap before reading a byte, then caps the streamed
# read so a lying or absent length cannot bypass it.

# ====== Third-Party Library Imports ======
from fastapi import HTTPException, Request
from loggerplusplus import loggerplusplus


class RequestBodyGuard:
    """Static helper that reads a request body under a hard byte ceiling (413 on overflow)."""

    logger = loggerplusplus.bind(identifier="RequestBodyGuard")

    def __new__(cls, *args: object, **kwargs: object) -> "RequestBodyGuard":
        raise TypeError("RequestBodyGuard is a static-only class and cannot be instantiated.")

    @classmethod
    def __reject(cls, max_bytes: int) -> None:
        """Log and raise the 413 for a body that crosses the ceiling."""
        cls.logger.warning(f"Rejected request body exceeding {max_bytes} bytes")
        raise HTTPException(
            status_code=413,
            detail={"error": f"request body exceeds the {max_bytes}-byte limit"},
        )

    @classmethod
    async def read_capped(cls, request: Request, max_bytes: int) -> bytes:
        """
        Read the full request body, refusing (413) as soon as it would exceed ``max_bytes``.

        Args:
            request (Request): The incoming request whose raw body is the payload.
            max_bytes (int): The hard ceiling in bytes.

        Returns:
            bytes: The buffered body (at most ``max_bytes``).

        Raises:
            HTTPException: 413 when the declared Content-Length OR the streamed size exceeds the cap.
        """
        # 1. Fast path — a declared Content-Length over the cap is refused before any byte is read.
        declared = request.headers.get("content-length")
        if declared is not None:
            try:
                if int(declared) > max_bytes:
                    cls.__reject(max_bytes)
            except ValueError:
                pass  # Malformed header — the streamed cap below still bounds the read.

        # 2. Stream with a running total so a lying/absent Content-Length cannot bypass the cap.
        chunks: list[bytes] = []
        total = 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > max_bytes:
                cls.__reject(max_bytes)
            chunks.append(chunk)
        return b"".join(chunks)


__all__ = ["RequestBodyGuard"]
