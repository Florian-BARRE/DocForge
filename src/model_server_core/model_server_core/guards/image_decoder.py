# ====== Code Summary ======
# ImageDecoder: verifies that raw bytes are a structurally valid image with Pillow's cheap `verify()`
# (no full pixel decode). Pillow is NOT a dependency of the core: the model server that wants this
# decoder depends on it, and the import is deferred so importing the core never loads it.

# ====== Standard Library Imports ======
from __future__ import annotations

import io

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from model_server_core.errors import InvalidInputError

# ====== Local Project Imports ======
from .media_decoder import MediaDecoder, MediaKind


class ImageDecoder(MediaDecoder, LoggerClass):
    """Image check backed by Pillow (provided by the model server, imported lazily)."""

    kind = MediaKind.IMAGE

    def __init__(self) -> None:
        LoggerClass.__init__(self)

    def verify(self, data: bytes) -> None:
        """Verify that `data` decodes as a supported image.

        Args:
            data (bytes): The request body (the image bytes).

        Raises:
            InvalidInputError: If the bytes are not a decodable image.
            ModuleNotFoundError: If the server did not depend on Pillow (a wiring error).
        """
        # 1. Deferred import: Pillow belongs to the server that uses this decoder, not to the core.
        from PIL import Image, UnidentifiedImageError  # noqa: PLC0415

        # 2. `verify()` checks structural integrity cheaply; it consumes the image object, which is
        #    fine since the route re-reads the bytes downstream.
        try:
            with Image.open(io.BytesIO(data)) as image:
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
            self.logger.warning(f"Rejected undecodable image body ({len(data)} bytes): {exc}")
            raise InvalidInputError("request body is not a decodable image") from exc
