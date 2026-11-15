# ====== Code Summary ======
# Behaviour of PdfDecoder against a fake pypdfium2 module (an optional dependency of the model server
# that uses the decoder, never of the core): a PDF with pages passes, an unparsable or page-less one is
# an InvalidInputError, the document is always closed, a missing pypdfium2 is a loud wiring error.

# ====== Standard Library Imports ======
import sys
import types

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from model_server_core import InvalidInputError, MediaKind, PdfDecoder


class _PdfiumError(Exception):
    """Stand-in for pypdfium2.PdfiumError."""


class _FakeDocument:
    """Document with as many pages as the payload has 'P' characters; b'BAD' fails to parse."""

    closed: list[bool] = []

    def __init__(self, data: bytes) -> None:
        if data == b"BAD":
            raise _PdfiumError("Failed to load document")
        self._pages = data.count(b"P")

    def __len__(self) -> int:
        return self._pages

    def close(self) -> None:
        _FakeDocument.closed.append(True)


def _install_fake_pdfium(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeDocument.closed = []
    module = types.ModuleType("pypdfium2")
    module.PdfDocument = _FakeDocument  # type: ignore[attr-defined]
    module.PdfiumError = _PdfiumError  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pypdfium2", module)


def test_a_pdf_with_pages_passes_and_is_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_pdfium(monkeypatch)

    PdfDecoder().verify(b"PP")

    assert _FakeDocument.closed == [True]


def test_an_unparsable_pdf_is_an_invalid_input(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_pdfium(monkeypatch)

    with pytest.raises(InvalidInputError, match="not a decodable PDF"):
        PdfDecoder().verify(b"BAD")


def test_a_pdf_without_pages_is_an_invalid_input_and_is_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_pdfium(monkeypatch)

    with pytest.raises(InvalidInputError, match="no pages"):
        PdfDecoder().verify(b"x")

    assert _FakeDocument.closed == [True]


def test_a_missing_pypdfium2_is_a_wiring_error_not_an_invalid_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "pypdfium2", None)

    with pytest.raises(ImportError):
        PdfDecoder().verify(b"PP")


def test_the_decoder_serves_the_pdf_kind() -> None:
    assert PdfDecoder().kind is MediaKind.PDF
