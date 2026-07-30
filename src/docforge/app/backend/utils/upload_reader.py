# ====== Code Summary ======
# UploadReader — a bounded, streaming reader for uploaded files. It exists to keep the admission
# path safe from an OOM DoS: instead of buffering the whole body into RAM and hashing it in one
# blocking call, it (a) rejects a grossly oversized upload on its declared Content-Length before a
# single byte is read, then (b) streams the body in fixed windows, content-addressing it (sha256)
# as it goes and aborting the instant the cumulative size crosses the collection's ceiling. The full
# bytes are still returned (S3 needs them), but never accumulated past the limit.

# ====== Standard Library Imports ======
import hashlib

# ====== Third-Party Library Imports ======
from fastapi import HTTPException, Request, UploadFile
from loggerplusplus import loggerplusplus


class UploadReader:
    """Static helpers that read an upload safely: an early size gate + a capped streaming hash."""

    logger = loggerplusplus.bind(identifier="UploadReader")

    # The streaming window — bounds peak memory growth while the body is consumed and hashed.
    _CHUNK_SIZE = 1024 * 1024

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("UploadReader is a static-only class and cannot be instantiated.")

    @classmethod
    def reject_oversized_body(cls, request: Request, limit: int) -> None:
        """
        Reject a DoS-sized upload on its declared Content-Length, before reading anything.

        The request Content-Length covers the whole multipart body (slightly larger than the file
        itself), so this is a conservative pre-filter — the precise per-byte enforcement is
        ``read_capped``. A missing or unparseable header is not fatal here: the streaming cap still
        guarantees the real ceiling is honoured.

        Args:
            request (Request): The incoming request (source of the Content-Length header).
            limit (int): The collection's ``max_file_size_bytes``.

        Raises:
            HTTPException: 422 when the declared body size exceeds the limit.
        """
        # 1. No (or unparseable) Content-Length → defer entirely to the streaming cap.
        raw = request.headers.get("content-length")
        if raw is None:
            return
        try:
            declared = int(raw)
        except ValueError:
            return

        # 2. A declared body above the ceiling is refused before any byte is buffered.
        if declared > limit:
            raise HTTPException(
                status_code=422,
                detail=f"Upload exceeds the collection's limit "
                f"(declared {declared} > {limit} bytes).",
            )

    @classmethod
    async def read_capped(cls, file: UploadFile, limit: int) -> tuple[bytes, str]:
        """
        Stream the upload in bounded windows, hashing as it goes, aborting past ``limit``.

        Accumulates the full bytes (S3 storage needs them) but never past the ceiling: the instant
        the cumulative size crosses ``limit`` it raises, so an oversized body is never fully
        buffered. The digest is byte-identical to hashing the whole content in one pass.

        Args:
            file (UploadFile): The multipart upload to consume.
            limit (int): The collection's ``max_file_size_bytes`` (strict ceiling).

        Returns:
            tuple[bytes, str]: The full content and its sha256 hex digest.

        Raises:
            HTTPException: 422 the moment the cumulative size exceeds ``limit``.
        """
        # 1. Consume the body in fixed windows, folding each into the running hash + buffer.
        hasher = hashlib.sha256()
        buffer = bytearray()
        while True:
            chunk = await file.read(cls._CHUNK_SIZE)
            if not chunk:
                break
            buffer.extend(chunk)
            hasher.update(chunk)
            # 2. Abort the instant the ceiling is crossed — never buffer an oversized body whole.
            if len(buffer) > limit:
                raise HTTPException(
                    status_code=422,
                    detail=f"File exceeds the collection's limit (> {limit} bytes).",
                )

        # 3. Full bytes + their content address.
        return bytes(buffer), hasher.hexdigest()


__all__ = ["UploadReader"]
