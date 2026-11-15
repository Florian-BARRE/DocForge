# ====== Code Summary ======
# InputValidator: runs the cheap pre-model checks on a raw request body BEFORE the expensive predict():
# non-empty, within the size cap, and decodable as the media type the route expects. A malformed
# upload is a CLIENT error (InvalidInputError -> HTTP 422), not a server fault reaching the model.
# Configured from the ServerConfig (size cap) with one MediaDecoder per accepted media kind.

# ====== Standard Library Imports ======
from __future__ import annotations

from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from model_server_core.config import ServerConfig
from model_server_core.errors import InvalidInputError

# ====== Local Project Imports ======
from .image_decoder import ImageDecoder
from .media_decoder import MediaDecoder, MediaKind
from .pdf_decoder import PdfDecoder


class InputValidator(LoggerClass):
    """Validates raw bodies against the media kinds the server accepts.

    Args:
        max_bytes (int): Size cap of a body (`ServerConfig.MAX_BODY_BYTES`), defence in depth next to
            `RequestBodyGuard`.
        decoders (Sequence[MediaDecoder]): One decoder per accepted media kind.

    Raises:
        ValueError: If `max_bytes` is not positive or two decoders share a kind.
    """

    # Public attributes
    max_bytes: int

    # Private attributes
    _decoders: dict[MediaKind, MediaDecoder]

    def __init__(self, *, max_bytes: int, decoders: Sequence[MediaDecoder]) -> None:
        LoggerClass.__init__(self)
        if max_bytes < 1:
            raise ValueError(f"max_bytes must be >= 1, got {max_bytes}")
        self.max_bytes = max_bytes
        self._decoders = {}
        for decoder in decoders:
            if decoder.kind in self._decoders:
                raise ValueError(f"two decoders registered for media kind '{decoder.kind.value}'")
            self._decoders[decoder.kind] = decoder

    # =======================
    #   Constructors
    # =======================
    @classmethod
    def from_config(
        cls, config: type[ServerConfig], decoders: Sequence[MediaDecoder] | None = None
    ) -> InputValidator:
        """Build a validator whose size cap comes from the configuration.

        Args:
            config (type[ServerConfig]): The injected configuration.
            decoders (Sequence[MediaDecoder] | None): Accepted media kinds; image and PDF by default.

        Returns:
            InputValidator: The configured validator.
        """
        chosen = decoders if decoders is not None else (ImageDecoder(), PdfDecoder())
        return cls(max_bytes=config.MAX_BODY_BYTES, decoders=chosen)

    # =======================
    #   Public Methods
    # =======================
    def validate(self, kind: MediaKind, data: bytes) -> None:
        """Check that `data` is a non-empty, in-cap, decodable body of `kind`.

        Args:
            kind (MediaKind): The media type the route expects.
            data (bytes): The request body.

        Raises:
            InvalidInputError: If the body is empty, too large, or not a decodable `kind`.
            LookupError: If no decoder is registered for `kind` (a wiring error).
        """
        # 1. A wiring error must be loud, never a silent "valid".
        decoder = self._decoders.get(kind)
        if decoder is None:
            raise LookupError(f"no decoder registered for media kind '{kind.value}'")

        # 2. Cheap structural checks first, the decoder last.
        if not data:
            raise InvalidInputError("request body is empty")
        if len(data) > self.max_bytes:
            raise InvalidInputError(f"request body exceeds the {self.max_bytes}-byte limit")
        decoder.verify(data)

    def verify_image(self, data: bytes) -> None:
        """Shorthand for `validate(MediaKind.IMAGE, data)`."""
        self.validate(MediaKind.IMAGE, data)

    def verify_pdf(self, data: bytes) -> None:
        """Shorthand for `validate(MediaKind.PDF, data)`."""
        self.validate(MediaKind.PDF, data)
