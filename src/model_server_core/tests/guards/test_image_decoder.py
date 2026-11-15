# ====== Code Summary ======
# Behaviour of ImageDecoder against a fake Pillow module (Pillow is an optional dependency of the model
# server that uses the decoder, never of the core): a structurally valid image passes, an undecodable
# one is an InvalidInputError, a missing Pillow is a loud wiring error.

# ====== Standard Library Imports ======
import sys
import types

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from model_server_core import ImageDecoder, InvalidInputError, MediaKind


class _UnidentifiedImageError(Exception):
    """Stand-in for PIL.UnidentifiedImageError."""


class _FakeImage:
    """Context-manager image whose verify() accepts only the bytes b'GOOD'."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def __enter__(self) -> "_FakeImage":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def verify(self) -> None:
        if self._data != b"GOOD":
            raise OSError("cannot identify image file")


def _install_fake_pillow(monkeypatch: pytest.MonkeyPatch) -> None:
    image_module = types.ModuleType("PIL.Image")
    image_module.open = lambda stream: _FakeImage(stream.getvalue())  # type: ignore[attr-defined]
    pil = types.ModuleType("PIL")
    pil.Image = image_module  # type: ignore[attr-defined]
    pil.UnidentifiedImageError = _UnidentifiedImageError  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "PIL", pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", image_module)


def test_a_valid_image_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_pillow(monkeypatch)

    ImageDecoder().verify(b"GOOD")


def test_an_undecodable_image_is_an_invalid_input(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_pillow(monkeypatch)

    with pytest.raises(InvalidInputError, match="not a decodable image"):
        ImageDecoder().verify(b"nope")


def test_a_missing_pillow_is_a_wiring_error_not_an_invalid_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "PIL", None)

    with pytest.raises(ImportError):
        ImageDecoder().verify(b"GOOD")


def test_the_decoder_serves_the_image_kind() -> None:
    assert ImageDecoder().kind is MediaKind.IMAGE
