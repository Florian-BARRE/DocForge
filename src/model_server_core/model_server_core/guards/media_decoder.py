# ====== Code Summary ======
# MediaDecoder: the contract of a cheap "does this body decode as this media type?" check, and the
# MediaKind enumeration of the media types the model hosts accept. A decoder wraps an optional heavy
# library (Pillow, pypdfium2) behind a lazy import, so the core never depends on it.

# ====== Standard Library Imports ======
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum


class MediaKind(str, Enum):
    """Closed set of media types a raw request body can be checked against."""

    IMAGE = "image"
    PDF = "pdf"


class MediaDecoder(ABC):
    """Contract: verify, without a full decode, that raw bytes are a valid `kind`."""

    # Public attributes
    kind: MediaKind

    @abstractmethod
    def verify(self, data: bytes) -> None:
        """Check that `data` decodes as `kind`.

        Args:
            data (bytes): The request body.

        Raises:
            InvalidInputError: If the bytes are not a decodable `kind`.
        """
