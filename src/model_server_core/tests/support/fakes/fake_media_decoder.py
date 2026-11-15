# ====== Code Summary ======
# FakeMediaDecoder: a MediaDecoder double that accepts or rejects every body, and counts its calls.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Internal Project Imports ======
from model_server_core import InvalidInputError, MediaDecoder, MediaKind


class FakeMediaDecoder(MediaDecoder):
    """Accepts every body, or rejects it with InvalidInputError when `reject` is set."""

    def __init__(self, kind: MediaKind, *, reject: bool = False) -> None:
        self.kind = kind
        self._reject = reject
        self.seen: list[bytes] = []

    def verify(self, data: bytes) -> None:
        self.seen.append(data)
        if self._reject:
            raise InvalidInputError(f"not a decodable {self.kind.value}")
