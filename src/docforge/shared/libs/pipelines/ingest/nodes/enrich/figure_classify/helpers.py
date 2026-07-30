# ====== Code Summary ======
# Static helpers of the figure classifier: cheap PNG dimension reading (IHDR header parse — no
# imaging library needed) and the normalization of a model answer into one of the FigureKind
# values.

# ====== Standard Library Imports ======
import struct

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.public_models import FigureKind

# The 8-byte PNG signature every valid PNG starts with.
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class FigureClassifyHelpers:
    """Static utility helpers for FigureClassifyNode."""

    logger = loggerplusplus.bind(identifier="FigureClassifyHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("FigureClassifyHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def png_dimensions(image: bytes) -> tuple[int, int] | None:
        """
        Read a PNG's (width, height) from its IHDR header — no decoder needed.

        Args:
            image (bytes): The crop bytes.

        Returns:
            tuple[int, int] | None: (width, height), or None when not a readable PNG.
        """
        # 1. Signature + IHDR live in the first 24 bytes of every valid PNG.
        if len(image) < 24 or not image.startswith(_PNG_SIGNATURE):
            return None
        width, height = struct.unpack(">II", image[16:24])
        return width, height

    @classmethod
    def parse_kind(cls, answer: str) -> str | None:
        """
        Normalize a model answer into one of the FigureKind values.

        Args:
            answer (str): The raw model output (expected: one class word).

        Returns:
            str | None: The matched kind value, or None when unrecognisable.
        """
        # 1. A well-behaved answer is one word; scan it against the known kinds.
        normalized = answer.strip().lower()
        for kind in FigureKind:
            if kind.value in normalized:
                return kind.value
        cls.logger.debug(f"Unrecognisable classification answer: {answer!r}")
        return None


__all__ = ["FigureClassifyHelpers"]
